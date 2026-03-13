"""
LangGraph node functions for the GBADS generation workflow.

Each node receives the full GBADSState, does its work, and returns a (partial)
dict that LangGraph merges back into the state.

Nodes set the correlation_id ContextVar at the top so that every log line
emitted inside the node carries the correct request/session ID.
"""
import logging
from typing import Optional

from sqlalchemy import select

from codegen.agent import CodegenAgent
from codegen.context import ContextBuilder
from config import get_settings
from database import get_session_factory
from git_manager import (
    commit_iteration,
    get_repo_file_tree,
    push_feature_branch,
    read_key_files,
    reset_to_best_iteration,
    summarize_diff,
    write_generated_code_to_repo,
)
from langgraph_workflow.state import GBADSState
from llm.client import LLMClient
from logging_config import correlation_id_var
from models import Feature, FeatureStatus, Iteration, Session
from runner.sandbox import run_in_sandbox
from time_utils import utc_now_naive

logger = logging.getLogger(__name__)

_ctx_builder = ContextBuilder()


# ── Node: setup_context ──────────────────────────────────────────────────────


async def setup_context(state: GBADSState) -> dict:
    """Build repo_context from the local repository (file tree + key files).

    This runs once at workflow start.  If there is no local_path the node is
    a no-op and the workflow proceeds with repo_context=None.
    """
    correlation_id_var.set(state["correlation_id"])
    local_path = state.get("local_path")

    if not local_path:
        logger.info("setup_context: no local_path — skipping repo context build")
        return {"repo_context": None}

    logger.info("setup_context: building repo context from %s", local_path)
    repo_context = {
        "file_tree": get_repo_file_tree(local_path),
        "key_files": read_key_files(local_path),
        "detected_stack": (state.get("compose_result") or {}).get("detected_stack"),
    }
    return {"repo_context": repo_context}


# ── Node: generate_code ──────────────────────────────────────────────────────


async def generate_code(state: GBADSState) -> dict:
    """Increment the iteration counter and generate code via CodegenAgent."""
    correlation_id_var.set(state["correlation_id"])

    iteration_number = state["iteration_number"] + 1
    logger.info(
        "generate_code: starting iteration %d/%d (session=%s)",
        iteration_number,
        state["max_iterations"],
        state["session_id"][:8],
    )

    llm = LLMClient(session_id=state["session_id"])
    llm.set_call_context(iteration_number=iteration_number)
    codegen = CodegenAgent(llm)

    context = _ctx_builder.build(
        iteration_number,
        (state.get("best_iteration_entry") or {}).get("iteration_number"),
        state.get("history", []),
    )

    local_path = state.get("local_path")
    repo_context = state.get("repo_context")
    compose_result = state.get("compose_result") or {}

    if local_path and repo_context:
        target_file, code, _ = await codegen.generate_with_target(
            state["spec"],
            _suite_from_state(state),
            context,
            repo_context=repo_context,
            connection_env_vars=compose_result.get("env_vars", {}),
        )
        write_generated_code_to_repo(local_path, target_file, code)
    else:
        code = await codegen.generate(state["spec"], _suite_from_state(state), context)
        module_name = state["spec"].get("module_name", "module")
        target_file = f"{module_name}.py"

    return {
        "iteration_number": iteration_number,
        "generated_code": code,
        "target_file": target_file,
    }


# ── Node: run_sandbox ────────────────────────────────────────────────────────


async def run_sandbox(state: GBADSState) -> dict:
    """Execute the generated code in a Docker sandbox and collect results."""
    correlation_id_var.set(state["correlation_id"])
    logger.info(
        "run_sandbox: iteration=%d session=%s",
        state["iteration_number"],
        state["session_id"][:8],
    )

    compose_result = state.get("compose_result") or {}
    test_cases_list = state["suite_dict"]

    sandbox_result = run_in_sandbox(
        state["generated_code"],
        test_cases_list,
        state["session_id"],
        state["project_id"],
        compose_result,
    )

    passed = sandbox_result.get("passed", 0)
    total = sandbox_result.get("total", len(test_cases_list))
    score = passed / total if total > 0 else 0.0

    logger.info(
        "run_sandbox: score=%.3f passed=%d/%d",
        score,
        passed,
        total,
    )
    return {"sandbox_result": sandbox_result}


# ── Node: commit_and_track ───────────────────────────────────────────────────


async def commit_and_track(state: GBADSState) -> dict:
    """Commit the generated code, persist the Iteration record, and track best."""
    correlation_id_var.set(state["correlation_id"])

    sandbox_result = state["sandbox_result"] or {}
    passed = sandbox_result.get("passed", 0)
    failed = sandbox_result.get("failed", 0)
    total = sandbox_result.get("total", len(state["suite_dict"]))
    score = passed / total if total > 0 else 0.0

    local_path = state.get("local_path")
    commit_hash: Optional[str] = None
    diff = ""

    if local_path:
        commit_hash, diff = commit_iteration(
            local_path, state["session_id"], state["iteration_number"], score, passed, total
        )

    diff_summary = summarize_diff(diff) if diff else ""
    is_best = score > state["best_score"]

    # Persist to DB
    factory = get_session_factory()
    async with factory() as db:
        iteration = Iteration(
            session_id=state["session_id"],
            iteration_number=state["iteration_number"],
            score=score,
            passed=passed,
            failed=failed,
            total=total,
            code=state["generated_code"],
            result_json=sandbox_result,
            commit_hash=commit_hash,
            diff=diff,
            is_best=is_best,
            created_at=utc_now_naive(),
        )
        db.add(iteration)
        await db.commit()

    entry = {
        "iteration_number": state["iteration_number"],
        "score": score,
        "diff_summary": diff_summary,
        "failed_details": sandbox_result.get("results", []),
    }
    history = list(state.get("history") or []) + [entry]

    updates: dict = {"history": history}

    if is_best:
        updates["best_score"] = score
        updates["best_commit_hash"] = commit_hash
        updates["best_iteration_entry"] = entry
        logger.info(
            "commit_and_track: new best iter=%d score=%.3f (%d/%d)",
            state["iteration_number"],
            score,
            passed,
            total,
        )
    else:
        logger.info(
            "commit_and_track: iter=%d score=%.3f (%d/%d) — not an improvement",
            state["iteration_number"],
            score,
            passed,
            total,
        )

    return updates


# ── Node: check_target ───────────────────────────────────────────────────────


async def check_target(state: GBADSState) -> dict:
    """No-op routing node.

    The actual branching decision is made by ``should_continue`` below which is
    wired as a conditional edge, so this node just passes state through.
    """
    correlation_id_var.set(state["correlation_id"])
    return {}


def should_continue(state: GBADSState) -> str:
    """Conditional edge function: decide whether to loop or finalize."""
    if state["best_score"] >= state["target_score"]:
        logger.info(
            "should_continue: target score %.3f reached → finalizing",
            state["target_score"],
        )
        return "finalize"
    if state["iteration_number"] >= state["max_iterations"]:
        logger.info(
            "should_continue: max iterations %d reached → finalizing",
            state["max_iterations"],
        )
        return "finalize"
    return "generate_code"


# ── Node: finalize ────────────────────────────────────────────────────────────


async def finalize(state: GBADSState) -> dict:
    """Push the best commit to GitHub and update Feature/Session status in DB."""
    correlation_id_var.set(state["correlation_id"])
    settings = get_settings()

    local_path = state.get("local_path")
    branch_name = state.get("branch_name")
    best_commit = state.get("best_commit_hash")

    if local_path and best_commit and branch_name:
        logger.info("finalize: resetting to best commit %s", best_commit[:8])
        reset_to_best_iteration(local_path, best_commit)
        push_feature_branch(local_path, branch_name, state["access_token"])
        logger.info("finalize: pushed branch %s", branch_name)

    pushed_at = utc_now_naive()
    best_score = state["best_score"]
    final_status = (
        FeatureStatus.DONE if best_score >= settings.target_score else FeatureStatus.PARTIAL
    )

    factory = get_session_factory()
    async with factory() as db:
        feat_result = await db.execute(
            select(Feature).where(Feature.id == state["feature_id"])
        )
        feat = feat_result.scalar_one_or_none()
        if feat:
            feat.status = final_status

        sess_result = await db.execute(
            select(Session).where(Session.id == state["session_id"])
        )
        sess = sess_result.scalar_one_or_none()
        if sess:
            sess.status = "completed"
            sess.best_score = best_score
            if local_path and best_commit:
                sess.pushed_at = pushed_at
                sess.push_commit_hash = best_commit
        await db.commit()

    logger.info(
        "finalize: feature=%s status=%s best_score=%.3f",
        state["feature_id"][:8],
        final_status,
        best_score,
    )
    return {}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _suite_from_state(state: GBADSState):
    """Reconstruct a TestSuite from the serialised suite_dict in state."""
    from benchmark.cases import MatchStrategy, TestCase, TestSuite

    cases = []
    for raw in state["suite_dict"]:
        strategy_val = raw.get("match_strategy", "exact")
        try:
            strategy = MatchStrategy(strategy_val)
        except ValueError:
            strategy = MatchStrategy.exact

        cases.append(
            TestCase(
                id=raw.get("id", "tc_000"),
                category=raw.get("category", "happy_path"),
                input=raw.get("input", {}),
                expected=raw.get("expected", {}),
                match_strategy=strategy,
                description=raw.get("description"),
            )
        )

    spec = state.get("spec", {})
    return TestSuite(
        module_name=spec.get("module_name", "module"),
        total_cases=len(cases),
        cases=cases,
    )
