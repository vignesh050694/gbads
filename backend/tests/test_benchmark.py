"""
Unit tests for benchmark match logic and data structures.
Run with: pytest tests/test_benchmark.py -v
"""
import pytest

from benchmark.cases import BenchmarkResult, CaseResult, MatchStrategy, TestCase, TestSuite
from benchmark.match import match_contains, match_exact, match_result, match_schema


# ---------------------------------------------------------------------------
# match_exact
# ---------------------------------------------------------------------------

class TestMatchExact:
    def test_equal_dicts(self):
        assert match_exact({"a": 1}, {"a": 1})

    def test_unequal_dicts(self):
        assert not match_exact({"a": 1}, {"a": 2})

    def test_equal_strings(self):
        assert match_exact("hello", "hello")

    def test_unequal_strings(self):
        assert not match_exact("hello", "world")

    def test_none_values(self):
        assert match_exact(None, None)
        assert not match_exact(None, 0)

    def test_nested_dicts(self):
        assert match_exact({"a": {"b": 1}}, {"a": {"b": 1}})
        assert not match_exact({"a": {"b": 1}}, {"a": {"b": 2}})

    def test_lists(self):
        assert match_exact([1, 2, 3], [1, 2, 3])
        assert not match_exact([1, 2], [1, 2, 3])


# ---------------------------------------------------------------------------
# match_schema
# ---------------------------------------------------------------------------

class TestMatchSchema:
    def test_same_shape_dict(self):
        actual = {"token": "eyJhb...", "expires_in": 3600}
        expected = {"token": "any_string", "expires_in": 0}
        assert match_schema(actual, expected)

    def test_missing_key(self):
        actual = {"token": "eyJhb..."}
        expected = {"token": "x", "expires_in": 0}
        assert not match_schema(actual, expected)

    def test_type_mismatch(self):
        actual = {"count": "not_an_int"}
        expected = {"count": 0}
        assert not match_schema(actual, expected)

    def test_nested_schema(self):
        actual = {"user": {"id": 99, "name": "Alice"}}
        expected = {"user": {"id": 0, "name": ""}}
        assert match_schema(actual, expected)

    def test_empty_list_matches_any_list(self):
        # Empty actual list is valid for any list schema
        assert match_schema([], [{"id": 0}])


# ---------------------------------------------------------------------------
# match_contains
# ---------------------------------------------------------------------------

class TestMatchContains:
    def test_superset(self):
        actual = {"a": 1, "b": 2, "c": 3}
        expected = {"a": 1}
        assert match_contains(actual, expected)

    def test_exact_match(self):
        actual = {"a": 1}
        expected = {"a": 1}
        assert match_contains(actual, expected)

    def test_missing_key(self):
        actual = {"a": 1}
        expected = {"a": 1, "b": 2}
        assert not match_contains(actual, expected)

    def test_nested_contains(self):
        actual = {"user": {"id": 1, "name": "Alice", "role": "admin"}}
        expected = {"user": {"id": 1}}
        assert match_contains(actual, expected)

    def test_list_contains(self):
        actual = [1, 2, 3, 4]
        expected = [1, 3]
        assert match_contains(actual, expected)

    def test_wrong_type(self):
        assert not match_contains("string", {"key": "value"})


# ---------------------------------------------------------------------------
# match_result dispatcher
# ---------------------------------------------------------------------------

class TestMatchResult:
    def test_dispatches_exact(self):
        assert match_result({"a": 1}, {"a": 1}, MatchStrategy.exact)
        assert not match_result({"a": 1}, {"a": 2}, MatchStrategy.exact)

    def test_dispatches_schema(self):
        assert match_result({"tok": "abc"}, {"tok": "x"}, MatchStrategy.schema)

    def test_dispatches_contains(self):
        assert match_result({"a": 1, "b": 2}, {"a": 1}, MatchStrategy.contains)

    def test_custom_fn_falls_back_to_exact(self):
        assert match_result("same", "same", MatchStrategy.custom_fn)
        assert not match_result("diff", "same", MatchStrategy.custom_fn)


# ---------------------------------------------------------------------------
# Pydantic model construction
# ---------------------------------------------------------------------------

class TestDataStructures:
    def test_test_case_defaults(self):
        tc = TestCase(id="tc_001", category="happy_path", input={"x": 1}, expected={"y": 2})
        assert tc.match_strategy == MatchStrategy.exact
        assert tc.description is None

    def test_test_suite(self):
        cases = [
            TestCase(id="tc_001", category="happy_path", input={"x": 1}, expected={"y": 2}),
        ]
        suite = TestSuite(module_name="add", total_cases=1, cases=cases)
        assert suite.total_cases == 1
        runner_dict = suite.to_runner_dict()
        assert runner_dict["module_name"] == "add"
        assert len(runner_dict["cases"]) == 1
        assert runner_dict["cases"][0]["id"] == "tc_001"

    def test_benchmark_result(self):
        results = [CaseResult(id="tc_001", status="pass", duration_ms=5)]
        br = BenchmarkResult(run_id="test-run", score=1.0, total=1, passed=1, failed=0, results=results)
        d = br.to_dict()
        assert d["score"] == 1.0
        assert d["passed"] == 1
