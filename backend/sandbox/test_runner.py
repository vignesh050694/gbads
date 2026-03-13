"""
sandbox/test_runner.py — FIXED FILE. Never modify after initial creation.

This script runs INSIDE the Docker container.
- stdlib only (no pip installs)
- Reads /tests/benchmark.json
- Imports /module/<module_name>.py
- Calls module.run(input_dict) for each test case
- Writes JSON result to stdout and exits 0
"""
import importlib.util
import json
import sys
import time
import traceback


# ---------------------------------------------------------------------------
# Inline match logic (no external imports allowed inside Docker)
# ---------------------------------------------------------------------------

def _match_exact(actual, expected):
    return actual == expected


def _match_schema(actual, expected):
    if type(actual) != type(expected):
        return False
    if isinstance(expected, dict):
        if set(expected.keys()) != set(actual.keys()):
            return False
        return all(_match_schema(actual[k], expected[k]) for k in expected)
    if isinstance(expected, list):
        if not actual:
            return True
        return _match_schema(actual[0], expected[0]) if expected else True
    return True


def _match_contains(actual, expected):
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        return all(
            k in actual and _match_contains(actual[k], expected[k])
            for k in expected
        )
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return False
        return all(any(_match_contains(a, e) for a in actual) for e in expected)
    return actual == expected


def _match(actual, expected, strategy):
    if strategy == "exact":
        return _match_exact(actual, expected)
    if strategy == "schema":
        return _match_schema(actual, expected)
    if strategy == "contains":
        return _match_contains(actual, expected)
    # custom_fn — fall back to exact
    return _match_exact(actual, expected)


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def main():
    # Load benchmark
    try:
        with open("/tests/benchmark.json", "r") as f:
            suite = json.load(f)
    except Exception as exc:
        print(json.dumps({"error": f"Failed to load benchmark: {exc}"}))
        sys.exit(1)

    module_name = suite.get("module_name", "module")
    cases = suite.get("cases", [])
    run_id = suite.get("run_id", "unknown")

    # Load generated module
    module_path = f"/module/{module_name}.py"
    try:
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as exc:
        error_trace = traceback.format_exc()
        # All cases fail if module won't import
        results = [
            {
                "id": c["id"],
                "status": "error",
                "error": f"Module import failed: {exc}",
                "actual_output": None,
                "duration_ms": 0,
            }
            for c in cases
        ]
        total = len(cases)
        print(
            json.dumps(
                {
                    "run_id": run_id,
                    "score": 0.0,
                    "total": total,
                    "passed": 0,
                    "failed": total,
                    "results": results,
                    "import_error": error_trace,
                }
            )
        )
        sys.exit(0)

    results = []
    passed = 0

    for case in cases:
        case_id = case["id"]
        input_data = case["input"]
        expected = case["expected"]
        strategy = case.get("match_strategy", "exact")

        start = time.monotonic()
        try:
            actual = module.run(input_data)
            duration_ms = int((time.monotonic() - start) * 1000)
            ok = _match(actual, expected, strategy)
            if ok:
                passed += 1
                results.append(
                    {"id": case_id, "status": "pass", "duration_ms": duration_ms}
                )
            else:
                results.append(
                    {
                        "id": case_id,
                        "status": "fail",
                        "duration_ms": duration_ms,
                        "actual_output": actual,
                        "error": f"Output mismatch (strategy={strategy})",
                    }
                )
        except Exception as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            results.append(
                {
                    "id": case_id,
                    "status": "error",
                    "duration_ms": duration_ms,
                    "actual_output": None,
                    "error": traceback.format_exc(),
                }
            )

    total = len(cases)
    score = passed / total if total > 0 else 0.0

    output = {
        "run_id": run_id,
        "score": score,
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "results": results,
    }
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
