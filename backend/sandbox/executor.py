import asyncio
import json
import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Optional

import docker
import docker.errors

from benchmark.cases import BenchmarkResult, CaseResult, TestSuite
from sandbox.docker_config import (
    BENCHMARK_FILENAME,
    CONTAINER_MODULE_DIR,
    CONTAINER_TESTS_DIR,
    SANDBOX_CONFIG,
    TEST_RUNNER_FILENAME,
    TMP_BASE,
)

logger = logging.getLogger(__name__)

# Path to the locked test_runner.py on the host
_TEST_RUNNER_PATH = Path(__file__).parent / "test_runner.py"


def _prepare_run_dirs(run_id: str, module_name: str, code: str, suite: TestSuite) -> Path:
    """Write code and test files to host tmp dirs. Returns run_dir."""
    run_dir = Path(TMP_BASE) / run_id
    module_dir = run_dir / "module"
    tests_dir = run_dir / "tests"
    module_dir.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)

    # Write generated module
    (module_dir / f"{module_name}.py").write_text(code, encoding="utf-8")

    # Write test runner (locked file)
    shutil.copy(_TEST_RUNNER_PATH, tests_dir / TEST_RUNNER_FILENAME)

    # Write benchmark JSON (include run_id so runner can echo it back)
    runner_dict = suite.to_runner_dict()
    runner_dict["run_id"] = run_id
    (tests_dir / BENCHMARK_FILENAME).write_text(
        json.dumps(runner_dict, indent=2), encoding="utf-8"
    )
    return run_dir


def _run_container(run_id: str, run_dir: Path) -> tuple[str, str]:
    """Blocking Docker run. Returns (stdout, stderr)."""
    client = docker.from_env()
    module_dir = str(run_dir / "module")
    tests_dir = str(run_dir / "tests")

    volumes = {
        module_dir: {"bind": CONTAINER_MODULE_DIR, "mode": "ro"},
        tests_dir: {"bind": CONTAINER_TESTS_DIR, "mode": "ro"},
    }

    timeout = SANDBOX_CONFIG["timeout_seconds"]

    try:
        result = client.containers.run(
            image=SANDBOX_CONFIG["base_image"],
            command=["python", f"{CONTAINER_TESTS_DIR}/{TEST_RUNNER_FILENAME}"],
            volumes=volumes,
            network_mode=SANDBOX_CONFIG["network_mode"],
            mem_limit=SANDBOX_CONFIG["mem_limit"],
            cpu_quota=SANDBOX_CONFIG["cpu_quota"],
            read_only=SANDBOX_CONFIG["read_only"],
            auto_remove=SANDBOX_CONFIG["auto_remove"],
            stdout=True,
            stderr=True,
            detach=False,
        )
        # containers.run with detach=False returns bytes of stdout
        stdout = result.decode("utf-8") if isinstance(result, bytes) else str(result)
        return stdout, ""
    except docker.errors.ContainerError as exc:
        stderr = exc.stderr.decode("utf-8") if exc.stderr else str(exc)
        stdout = exc.stdout.decode("utf-8") if exc.stdout else ""
        logger.error("Container error for run %s: %s", run_id, stderr)
        return stdout, stderr
    except docker.errors.ImageNotFound as exc:
        raise RuntimeError(
            f"Docker image '{SANDBOX_CONFIG['base_image']}' not found. "
            "Run: docker pull python:3.11-slim"
        ) from exc
    except Exception as exc:
        logger.error("Docker run failed for %s: %s", run_id, exc)
        return "", str(exc)


def _parse_result(stdout: str, stderr: str, run_id: str) -> BenchmarkResult:
    """Parse stdout JSON into BenchmarkResult."""
    stdout = stdout.strip()
    # Find the last complete JSON object in stdout (ignore any print() from module)
    lines = stdout.splitlines()
    json_str = None
    for line in reversed(lines):
        line = line.strip()
        if line.startswith("{"):
            json_str = line
            break

    if not json_str:
        logger.error("No JSON found in container stdout. stderr=%s", stderr)
        return BenchmarkResult(
            run_id=run_id,
            score=0.0,
            total=0,
            passed=0,
            failed=0,
            results=[],
        )

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse result JSON: %s", exc)
        return BenchmarkResult(
            run_id=run_id,
            score=0.0,
            total=0,
            passed=0,
            failed=0,
            results=[],
        )

    results = [
        CaseResult(
            id=r["id"],
            status=r["status"],
            duration_ms=r.get("duration_ms"),
            error=r.get("error"),
            actual_output=r.get("actual_output"),
        )
        for r in data.get("results", [])
    ]

    return BenchmarkResult(
        run_id=run_id,
        score=data.get("score", 0.0),
        total=data.get("total", 0),
        passed=data.get("passed", 0),
        failed=data.get("failed", 0),
        results=results,
    )


def _cleanup(run_dir: Path) -> None:
    try:
        shutil.rmtree(run_dir, ignore_errors=True)
    except Exception as exc:
        logger.warning("Cleanup failed for %s: %s", run_dir, exc)


class SandboxExecutor:
    async def run(
        self,
        code: str,
        suite: TestSuite,
        run_id: Optional[str] = None,
    ) -> BenchmarkResult:
        """Run generated code against the test suite in a Docker sandbox."""
        if run_id is None:
            run_id = str(uuid.uuid4())

        module_name = suite.module_name
        run_dir = _prepare_run_dirs(run_id, module_name, code, suite)

        loop = asyncio.get_event_loop()
        try:
            stdout, stderr = await loop.run_in_executor(
                None, _run_container, run_id, run_dir
            )
        finally:
            _cleanup(run_dir)

        return _parse_result(stdout, stderr, run_id)
