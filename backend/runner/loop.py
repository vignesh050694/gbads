"""
Feature iteration loop for GBADS v2.
Handles the full autonomous loop: generate → sandbox → commit → repeat → push.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from benchmark.generator import BenchmarkGenerator
from codegen.agent import CodegenAgent
from codegen.context import ContextBuilder
from config import get_settings
from database import get_session_factory
from git_manager import (
    commit_iteration,
    create_feature_branch,
    get_repo_file_tree,
    push_feature_branch,
    read_key_files,
    reset_to_best_iteration,
    summarize_diff,
    write_generated_code_to_repo,
)
from agents.compose_agent import save_compose_file
from interceptor.agent import InterceptorAgent
from llm.client import LLMClient
from models import Feature, FeatureStatus, Iteration, Project, ProjectRepo, Session, User
from runner.sandbox import run_in_sandbox
from auth.github import decrypt_token
from time_utils import utc_now_naive

logger = logging.getLogger(__name__)


async def run_feature_loop(feature_id: str, session_id: str) -> None:
    """
    Full autonomous loop for a feature:
    1. Load feature + project + repo from DB
    2. Create feature branch
    3. Generate test suite
    4. Loop: codegen → sandbox → commit → track best
    5. Push best iteration to GitHub
    """
    settings = get_settings()
    factory = get_session_factory()

    async with factory() as db:
        # ── GATE ───────────────────────────────────────────────────────────────
        feat_result = await db.execute(select(Feature).where(Feature.id == feature_id))
        feature = feat_result.scalar_one_or_none()
        if not feature:
            raise ValueError(f"Feature {feature_id} not found")
        if not feature.approved_at:
            raise ValueError("Metric must be approved before loop starts")

        proj_result = await db.execute(select(Project).where(Project.id == feature.project_id))
        project = proj_result.scalar_one_or_none()

        user_result = await db.execute(select(User).where(User.id == project.user_id))
        user = user_result.scalar_one_or_none()
        access_token = decrypt_token(user.github_access_token)

        repo_result = await db.execute(
            select(ProjectRepo).where(
                ProjectRepo.project_id == project.id,
                ProjectRepo.clone_status == "DONE",
            )
        )
        repo = repo_result.scalar_one_or_none()
        local_path = repo.local_path if repo else None

        sess_result = await db.execute(select(Session).where(Session.id == session_id))
        session = sess_result.scalar_one_or_none()

    # ── SETUP ──────────────────────────────────────────────────────────────────
    llm = LLMClient(session_id=session_id)
    bench_gen = BenchmarkGenerator(llm)
    codegen = CodegenAgent(llm)
    ctx_builder = ContextBuilder()

    # Feature branch (if we have a real repo)
    branch_name = None
    if local_path:
        branch_name = create_feature_branch(local_path, session_id[:8])
        async with factory() as db:
            feat_result = await db.execute(select(Feature).where(Feature.id == feature_id))
            feat = feat_result.scalar_one_or_none()
            if feat:
                feat.feature_branch = branch_name
            sess_result = await db.execute(select(Session).where(Session.id == session_id))
            sess = sess_result.scalar_one_or_none()
            if sess:
                sess.feature_branch = branch_name
                sess.repo_path = local_path
            await db.commit()

    # Compose setup
    compose_result = {
        "needs_infra": bool(project.generated_compose),
        "compose_yaml": project.generated_compose,
        "env_vars": (project.detected_stack or {}).get("env_vars", {}),
    }
    if compose_result["needs_infra"] and local_path:
        compose_path = save_compose_file(project.id, session_id, compose_result["compose_yaml"])
        compose_result["compose_path"] = compose_path

    # Repo context
    repo_context = None
    if local_path:
        repo_context = {
            "file_tree": get_repo_file_tree(local_path),
            "key_files": read_key_files(local_path),
            "detected_stack": project.detected_stack,
        }

    # Generate full test suite
    llm.set_call_context(iteration_number=None)
    suite = await bench_gen.generate(feature.module_spec, {})

    effective_max = min(settings.max_iterations, settings.hard_ceiling)

    # ── LOOP ───────────────────────────────────────────────────────────────────
    best = {"score": 0.0, "commit_hash": None, "iteration": None}
    history = []

    for i in range(1, effective_max + 1):
        logger.info("Feature %s iter %d/%d", feature_id[:8], i, effective_max)

        llm.set_call_context(iteration_number=i)
        context = ctx_builder.build(i, best["iteration"], history)

        if local_path:
            target_file, code, tokens = await codegen.generate_with_target(
                feature.module_spec, suite, context,
                repo_context=repo_context,
                connection_env_vars=compose_result.get("env_vars", {}),
            )
            write_generated_code_to_repo(local_path, target_file, code)
        else:
            code = await codegen.generate(feature.module_spec, suite, context)
            target_file = f"{feature.module_spec.get('module_name', 'module')}.py"
            tokens = 0

        # Run sandbox
        test_cases_list = [
            {
                "id": tc.id, "category": tc.category,
                "input": tc.input, "expected": tc.expected,
                "match_strategy": tc.match_strategy.value,
                "description": tc.description,
            }
            for tc in suite.cases
        ]
        sandbox_result = run_in_sandbox(
            code, test_cases_list, session_id, project.id, compose_result
        )
        passed = sandbox_result.get("passed", 0)
        failed = sandbox_result.get("failed", 0)
        total = sandbox_result.get("total", len(test_cases_list))
        score = passed / total if total > 0 else 0.0

        # Commit if we have a real repo
        commit_hash = None
        diff = ""
        if local_path:
            commit_hash, diff = commit_iteration(local_path, session_id, i, score, passed, total)

        diff_summary = summarize_diff(diff) if diff else ""
        is_best = score > best["score"]

        # Persist iteration
        async with factory() as db:
            iteration = Iteration(
                session_id=session_id,
                iteration_number=i,
                score=score,
                passed=passed,
                failed=failed,
                total=total,
                code=code,
                result_json=sandbox_result,
                commit_hash=commit_hash,
                diff=diff,
                is_best=is_best,
                created_at=utc_now_naive(),
            )
            db.add(iteration)
            await db.commit()
            await db.refresh(iteration)
            iteration_id = iteration.id

        entry = {
            "iteration_number": i,
            "score": score,
            "diff_summary": diff_summary,
            "failed_details": sandbox_result.get("results", []),
        }
        history.append(entry)

        if is_best:
            best = {"score": score, "commit_hash": commit_hash, "iteration": entry}
            logger.info("New best: iter=%d score=%.3f (%d/%d)", i, score, passed, total)

        if score >= settings.target_score:
            logger.info("Target score reached at iteration %d!", i)
            break

    # ── PUSH BEST TO GITHUB ────────────────────────────────────────────────────
    if local_path and best["commit_hash"]:
        reset_to_best_iteration(local_path, best["commit_hash"])
        push_feature_branch(local_path, branch_name, access_token)
        pushed_at = utc_now_naive()

        async with factory() as db:
            sess_result = await db.execute(select(Session).where(Session.id == session_id))
            sess = sess_result.scalar_one_or_none()
            if sess:
                sess.pushed_at = pushed_at
                sess.push_commit_hash = best["commit_hash"]
            await db.commit()

    # ── FINALIZE ───────────────────────────────────────────────────────────────
    final_status = FeatureStatus.DONE if best["score"] >= settings.target_score else FeatureStatus.PARTIAL

    async with factory() as db:
        feat_result = await db.execute(select(Feature).where(Feature.id == feature_id))
        feat = feat_result.scalar_one_or_none()
        if feat:
            feat.status = final_status
        sess_result = await db.execute(select(Session).where(Session.id == session_id))
        sess = sess_result.scalar_one_or_none()
        if sess:
            sess.status = "completed"
            sess.best_score = best["score"]
        await db.commit()

    logger.info("Feature loop done: %s status=%s score=%.3f", feature_id[:8], final_status, best["score"])
