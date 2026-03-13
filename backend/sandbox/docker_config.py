"""
Docker sandbox configuration constants.
These values are fixed — never change network_mode or remove resource limits.
"""

SANDBOX_CONFIG = {
    "base_image": "python:3.11-slim",
    "network_mode": "none",   # NO network access — absolute, no exceptions
    "mem_limit": "256m",
    "cpu_quota": 50000,        # 0.5 CPU
    "read_only": False,        # container needs write for temp files
    "auto_remove": True,       # destroy container on exit
    "timeout_seconds": 30,     # hard kill after 30s
}

TMP_BASE = "/tmp/gbads"
CONTAINER_MODULE_DIR = "/module"
CONTAINER_TESTS_DIR = "/tests"
BENCHMARK_FILENAME = "benchmark.json"
TEST_RUNNER_FILENAME = "test_runner.py"
