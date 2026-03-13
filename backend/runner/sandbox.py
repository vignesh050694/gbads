"""
Sandbox execution with support for both compose-based (infra) and single-container sandboxes.
"""
import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from config import get_settings

logger = logging.getLogger(__name__)


def run_in_sandbox(
    generated_code: str,
    test_cases: list[dict],
    session_id: str,
    project_id: Optional[str],
    compose_result: Optional[dict] = None,
) -> dict:
    """
    Run generated code against test cases.
    Uses compose-based sandbox if compose_result["needs_infra"] is True,
    otherwise falls back to single-container sandbox.
    """
    if compose_result and compose_result.get("needs_infra"):
        scratch_dir = prepare_sandbox_files(
            session_id=session_id,
            project_id=project_id,
            generated_code=generated_code,
            test_cases=test_cases,
            env_vars=compose_result.get("env_vars", {}),
        )
        compose_path = compose_result.get("compose_path")
        if compose_path and Path(compose_path).exists():
            return run_compose_sandbox(compose_path, timeout=120)
        logger.warning("Compose path missing, falling back to single-container")

    return _run_single_container(generated_code, test_cases, session_id)


def prepare_sandbox_files(
    session_id: str,
    project_id: Optional[str],
    generated_code: str,
    test_cases: list[dict],
    env_vars: dict,
) -> str:
    """Write generated code + test runner to sandbox scratch dir."""
    settings = get_settings()

    if project_id:
        scratch = settings.workspace_base / project_id / "sandboxes" / session_id
    else:
        scratch = settings.output_dir / "sandboxes" / session_id

    scratch.mkdir(parents=True, exist_ok=True)

    (scratch / "module.py").write_text(generated_code, encoding="utf-8")
    (scratch / "test_cases.json").write_text(json.dumps(test_cases), encoding="utf-8")

    # Copy the fixed test runner
    test_runner_src = Path(__file__).parent.parent / "sandbox" / "test_runner.py"
    if test_runner_src.exists():
        (scratch / "test_runner.py").write_text(
            test_runner_src.read_text(encoding="utf-8"), encoding="utf-8"
        )

    return str(scratch)


def run_compose_sandbox(compose_path: str, timeout: int = 120) -> dict:
    """Run docker compose sandbox and parse results."""
    try:
        result = subprocess.run(
            [
                "docker", "compose", "-f", compose_path,
                "up", "--abort-on-container-exit",
                "--exit-code-from", "test-runner",
                "--no-color",
            ],
            timeout=timeout,
            capture_output=True,
            text=True,
        )
        output = result.stdout + result.stderr

        # Try to parse JSON from test-runner output
        parsed = _parse_test_runner_output(output)
        return parsed

    except subprocess.TimeoutExpired:
        logger.error("Compose sandbox timed out after %ds", timeout)
        return {"error": "timeout", "passed": 0, "failed": 0, "total": 0, "score": 0.0}
    except Exception as exc:
        logger.error("Compose sandbox error: %s", exc)
        return {"error": str(exc), "passed": 0, "failed": 0, "total": 0, "score": 0.0}
    finally:
        _cleanup_compose(compose_path)


def _cleanup_compose(compose_path: str) -> None:
    try:
        subprocess.run(
            ["docker", "compose", "-f", compose_path, "down", "-v", "--remove-orphans"],
            timeout=30,
            capture_output=True,
        )
    except Exception as exc:
        logger.warning("Compose cleanup failed: %s", exc)


def _parse_test_runner_output(output: str) -> dict:
    """Extract JSON result from test runner stdout."""
    for line in reversed(output.splitlines()):
        line = line.strip()
        if line.startswith("{") and "passed" in line:
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return {"error": "no_output", "passed": 0, "failed": 0, "total": 0, "score": 0.0}


def _run_single_container(
    generated_code: str,
    test_cases: list[dict],
    session_id: str,
) -> dict:
    """Fall back to the v1 single-container Docker sandbox."""
    from sandbox.executor import SandboxExecutor
    from benchmark.cases import TestCase, TestSuite, MatchStrategy
    import asyncio

    executor = SandboxExecutor()
    cases = []
    for tc in test_cases:
        try:
            strategy = MatchStrategy(tc.get("match_strategy", "exact"))
        except ValueError:
            strategy = MatchStrategy.exact
        cases.append(TestCase(
            id=tc.get("id", "tc_001"),
            category=tc.get("category", "happy_path"),
            input=tc.get("input", {}),
            expected=tc.get("expected", {}),
            match_strategy=strategy,
            description=tc.get("description"),
        ))

    suite = TestSuite(module_name="module", total_cases=len(cases), cases=cases)

    async def _run():
        return await executor.run(code=generated_code, suite=suite, run_id=session_id)

    result = asyncio.get_event_loop().run_until_complete(_run())
    return result.to_dict()
