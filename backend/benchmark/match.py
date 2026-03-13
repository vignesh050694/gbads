from typing import Any

from benchmark.cases import MatchStrategy


def match_exact(actual: Any, expected: Any) -> bool:
    """Deep equality check."""
    return actual == expected


def match_schema(actual: Any, expected: Any) -> bool:
    """Check that actual has the same keys and value types as expected.
    Values themselves are not compared — only structure and types.
    """
    if type(actual) != type(expected):
        return False
    if isinstance(expected, dict):
        if set(expected.keys()) != set(actual.keys()):
            return False
        return all(
            match_schema(actual[k], expected[k]) for k in expected
        )
    if isinstance(expected, list):
        if len(actual) == 0:
            return True  # empty list matches any list schema
        return match_schema(actual[0], expected[0]) if expected else True
    return True  # scalar — types already matched above


def match_contains(actual: Any, expected: Any) -> bool:
    """actual must contain all keys/values from expected (subset match)."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        return all(
            k in actual and match_contains(actual[k], expected[k])
            for k in expected
        )
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return False
        return all(any(match_contains(a, e) for a in actual) for e in expected)
    return actual == expected


def match_result(actual: Any, expected: Any, strategy: MatchStrategy) -> bool:
    """Dispatch to the appropriate match function."""
    if strategy == MatchStrategy.exact:
        return match_exact(actual, expected)
    if strategy == MatchStrategy.schema:
        return match_schema(actual, expected)
    if strategy == MatchStrategy.contains:
        return match_contains(actual, expected)
    # custom_fn — not implemented in this layer; test_runner handles inline
    return match_exact(actual, expected)
