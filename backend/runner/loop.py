"""
Feature iteration loop for GBADS v2.
Handles the full autonomous loop: generate → sandbox → commit → repeat → push.

The code-generation iteration loop is now implemented as a LangGraph workflow
(see ``langgraph_workflow/``).  This module keeps the surrounding orchestration:
loading entities from the DB, creating the feature branch, generating the test
suite, building the initial workflow state, and kicking off the graph.
"""
import logging
from typing import Optional

from sqlalchemy import select

from benchmark.generator import BenchmarkGenerator
from config import get_settings
from database import get_session_factory
from git_manager import create_feature_branch
from agents.compose_agent import save_compose_file
from langgraph_workflow.state import GBADSState
from langgraph_workflow.workflow import generation_workflow
from llm.client import LLMClient
from logging_config import correlation_id_var
from models import Feature, Project, ProjectRepo, Session, User
from auth.github import decrypt_token

logger = logging.getLogger(__name__)


async def run_feature_loop(feature_id: str, session_id: str) -> None:
    """
    Full autonomous loop for a feature:
    1. Load feature + project + repo from DB
    2. Create feature branch
    3. Generate test suite
    4. Run the LangGraph generation workflow
       (codegen → sandbox → commit → track best → push)
    """
    settings = get_settings()
    factory = get_session_factory()

    # Propagate the current correlation ID into all log messages for this loop.
    cid = correlation_id_var.get("-")

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

    # ── SETUP ──────────────────────────────────────────────────────────────────
    llm = LLMClient(session_id=session_id)
    bench_gen = BenchmarkGenerator(llm)

    # Feature branch (if we have a real repo)
    branch_name: Optional[str] = None
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
    compose_result: dict = {
        "needs_infra": bool(project.generated_compose),
        "compose_yaml": project.generated_compose,
        "env_vars": (project.detected_stack or {}).get("env_vars", {}),
    }
    if compose_result["needs_infra"] and local_path:
        compose_path = save_compose_file(project.id, session_id, compose_result["compose_yaml"])
        compose_result["compose_path"] = compose_path

    # Generate test suite (before the workflow starts)
    llm.set_call_context(iteration_number=None)
    suite = await bench_gen.generate(feature.module_spec, {})

    # Serialise suite cases for state passing
    suite_dict = [
        {
            "id": tc.id,
            "category": tc.category,
            "input": tc.input,
            "expected": tc.expected,
            "match_strategy": tc.match_strategy.value,
            "description": tc.description,
        }
        for tc in suite.cases
    ]

    effective_max = min(settings.max_iterations, settings.hard_ceiling)

    # ── LANGGRAPH WORKFLOW ──────────────────────────────────────────────────────
    logger.info(
        "run_feature_loop: starting LangGraph workflow feature=%s session=%s max_iter=%d",
        feature_id[:8],
        session_id[:8],
        effective_max,
    )

    initial_state: GBADSState = {
        "correlation_id": cid,
        "feature_id": feature_id,
        "session_id": session_id,
        "project_id": project.id,
        "access_token": access_token,
        "spec": feature.module_spec,
        "suite_dict": suite_dict,
        "iteration_number": 0,
        "max_iterations": effective_max,
        "target_score": settings.target_score,
        "generated_code": None,
        "target_file": None,
        "sandbox_result": None,
        "best_score": 0.0,
        "best_commit_hash": None,
        "best_iteration_entry": None,
        "history": [],
        "local_path": local_path,
        "branch_name": branch_name,
        "repo_context": None,   # populated by setup_context node
        "compose_result": compose_result,
        "error": None,
    }

    await generation_workflow.ainvoke(initial_state)

    logger.info(
        "run_feature_loop: workflow complete feature=%s session=%s",
        feature_id[:8],
        session_id[:8],
    )
