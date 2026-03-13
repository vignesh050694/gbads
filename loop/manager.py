import logging
import uuid
from pathlib import Path
from typing import Optional

import db.store as store
from benchmark.generator import BenchmarkGenerator
from codegen.agent import CodegenAgent
from codegen.context import ContextBuilder
from config import get_settings
from vcs.manager import GitManager
from interceptor.agent import InterceptorAgent
from llm.client import LLMClient
from sandbox.executor import SandboxExecutor

logger = logging.getLogger(__name__)


class LoopManager:
    def __init__(self):
        settings = get_settings()
        self._settings = settings
        self._llm = LLMClient()
        self._interceptor = InterceptorAgent(self._llm)
        self._benchmark_gen = BenchmarkGenerator(self._llm)
        self._codegen = CodegenAgent(self._llm)
        self._sandbox = SandboxExecutor()
        self._ctx_builder = ContextBuilder()

    async def run(
        self,
        requirement: str,
        user_examples: Optional[dict] = None,
        max_iterations: Optional[int] = None,
        session_id: Optional[str] = None,
        notify_callback=None,
    ) -> dict:
        """Run the full autonomous generation loop.

        Returns a dict: {
            session_id, spec, suite, best, history
        }
        """
        settings = self._settings
        user_examples = user_examples or {}

        effective_max = min(
            max_iterations or settings.max_iterations,
            settings.hard_ceiling,
        )

        # ------------------------------------------------------------------ #
        # Step 1: Parse requirement
        # ------------------------------------------------------------------ #
        logger.info("Parsing requirement...")
        spec = await self._interceptor.parse(requirement)

        # Surface clarifying questions if confidence is low
        if (
            spec.get("confidence_score", 1.0) < 0.7
            and spec.get("clarifying_questions")
            and notify_callback
        ):
            answers = await notify_callback("clarifying_questions", spec["clarifying_questions"])
            if answers:
                spec = await self._interceptor.parse(requirement, clarifications=answers)

        module_name = spec["module_name"]
        logger.info("Module: %s", module_name)

        # ------------------------------------------------------------------ #
        # Step 2: Create DB session
        # ------------------------------------------------------------------ #
        if session_id is None:
            session_id = await store.create_session(module_name, requirement)
        logger.info("Session ID: %s", session_id)

        # ------------------------------------------------------------------ #
        # Step 3: Generate benchmark test suite
        # ------------------------------------------------------------------ #
        logger.info("Generating test suite...")
        suite = await self._benchmark_gen.generate(spec, user_examples)
        logger.info("Test suite: %d cases", suite.total_cases)

        if notify_callback:
            await notify_callback("suite_ready", suite)

        # ------------------------------------------------------------------ #
        # Step 4: Set up git manager
        # ------------------------------------------------------------------ #
        output_dir = settings.output_dir / session_id[:8]
        git_mgr = GitManager(output_dir, module_name)

        # ------------------------------------------------------------------ #
        # Step 5: Iteration loop
        # ------------------------------------------------------------------ #
        best: dict = {
            "score": 0.0,
            "iteration": None,
            "code": None,
            "result": None,
            "diff_summary": "",
        }
        history: list[dict] = []

        for i in range(1, effective_max + 1):
            logger.info("=== Iteration %d / %d ===", i, effective_max)

            if notify_callback:
                await notify_callback("iteration_start", {"iteration": i, "max": effective_max})

            # Build context
            context = self._ctx_builder.build(i, best if best["iteration"] else None, history)

            # Generate code
            code = await self._codegen.generate(spec, suite, context)

            # Run in sandbox
            run_id = str(uuid.uuid4())
            result = await self._sandbox.run(code=code, suite=suite, run_id=run_id)

            # Git commit
            is_best = result.score > best["score"]
            git_mgr.commit_iteration(
                iteration=i,
                score=result.score,
                passed=result.passed,
                total=result.total,
                code=code,
                is_best=is_best,
            )
            diff_summary = git_mgr.get_diff_summary()

            # Save to DB
            await store.save_iteration(
                session_id=session_id,
                iteration_number=i,
                score=result.score,
                passed=result.passed,
                failed=result.failed,
                total=result.total,
                code=code,
                result_json=result.to_dict(),
            )

            entry = {
                "iteration": i,
                "score": result.score,
                "passed": result.passed,
                "failed": result.failed,
                "total": result.total,
                "code": code,
                "result": result.to_dict(),
                "diff_summary": diff_summary,
            }
            history.append(entry)

            if is_best:
                best = {
                    "score": result.score,
                    "iteration": i,
                    "code": code,
                    "result": result.to_dict(),
                    "diff_summary": diff_summary,
                }
                logger.info(
                    "New best at iteration %d: %.3f (%d/%d)",
                    i, result.score, result.passed, result.total,
                )

            if notify_callback:
                await notify_callback("iteration_done", {"iteration": i, "result": result, "best": best})

            # Early exit
            if result.score >= settings.target_score:
                logger.info("Target score reached at iteration %d!", i)
                break

        # ------------------------------------------------------------------ #
        # Step 6: Finalize
        # ------------------------------------------------------------------ #
        git_mgr.tag_head()

        # Write best code to output dir root
        if best["code"]:
            final_code_path = settings.output_dir / f"{module_name}.py"
            settings.output_dir.mkdir(parents=True, exist_ok=True)
            final_code_path.write_text(best["code"], encoding="utf-8")
            logger.info("Best code written to %s", final_code_path)

        # Update session status
        await store.update_session_status(
            session_id=session_id,
            status="completed",
            best_score=best["score"],
            best_iteration=best["iteration"],
        )

        return {
            "session_id": session_id,
            "spec": spec,
            "suite": suite,
            "best": best,
            "history": history,
            "git_log": git_mgr.get_session_log(),
        }

    async def resume(self, session_id: str) -> dict:
        """Resume from the best iteration of an existing session."""
        session = await store.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        best_iter = await store.get_best_iteration(session_id)
        if not best_iter:
            raise ValueError(f"No iterations found for session {session_id}")

        # Re-run from best iteration
        return await self.run(
            requirement=session["requirement"],
            session_id=session_id,
        )
