from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel


class MatchStrategy(str, Enum):
    exact = "exact"
    schema = "schema"
    contains = "contains"
    custom_fn = "custom_fn"


class TestCase(BaseModel):
    id: str
    category: str
    input: dict[str, Any]
    expected: Any
    match_strategy: MatchStrategy = MatchStrategy.exact
    description: Optional[str] = None


class CaseResult(BaseModel):
    id: str
    status: str  # "pass" | "fail" | "error"
    duration_ms: Optional[int] = None
    error: Optional[str] = None
    actual_output: Optional[Any] = None


class TestSuite(BaseModel):
    module_name: str
    total_cases: int
    cases: list[TestCase]

    def to_runner_dict(self) -> dict:
        """Serialize for use by the sandbox test_runner."""
        return {
            "module_name": self.module_name,
            "total_cases": self.total_cases,
            "cases": [
                {
                    "id": c.id,
                    "category": c.category,
                    "input": c.input,
                    "expected": c.expected,
                    "match_strategy": c.match_strategy.value,
                }
                for c in self.cases
            ],
        }


class BenchmarkResult(BaseModel):
    run_id: str
    score: float
    total: int
    passed: int
    failed: int
    results: list[CaseResult]

    def to_dict(self) -> dict:
        return self.model_dump()
