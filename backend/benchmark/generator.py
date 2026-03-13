import json
import logging
from typing import Any

from benchmark.cases import MatchStrategy, TestCase, TestSuite
from llm.client import LLMClient

logger = logging.getLogger(__name__)

GENERATOR_SYSTEM = """You are a rigorous test case generator for a software module.
Given a module spec and sample input/output examples, generate a comprehensive test suite.

Return ONLY a valid JSON array of test case objects. No prose, no markdown fences.

Each test case object must have:
- "id": string like "tc_001", "tc_002", ...
- "category": one of: happy_path, boundary, null_empty, type_mismatch, constraint_violation, security, idempotency
- "input": dict of input values
- "expected": expected output value or shape
- "match_strategy": one of: exact, schema, contains, custom_fn
  - Use "schema" for dynamic values like JWTs or UUIDs (check structure, not value)
  - Use "exact" for deterministic outputs
  - Use "contains" when only checking key presence
- "description": short human-readable description

Generate test cases across ALL 7 categories:
1. happy_path — valid inputs that should succeed
2. boundary — edge cases at constraint limits (min/max lengths, exact boundaries)
3. null_empty — missing fields, null values, empty strings
4. type_mismatch — wrong types (int where string expected, etc.)
5. constraint_violation — inputs that violate stated constraints
6. security — SQL injection, XSS payloads, oversized inputs
7. idempotency — same input called twice should return consistent output

Aim for ~20-30 total test cases. The module must expose a function called `run(input_dict) -> output`.
"""


def _make_fallback_suite(spec: dict, user_examples: dict) -> TestSuite:
    """Generate a minimal test suite without LLM when API fails."""
    cases = []
    idx = 1

    # Include user-provided happy path examples
    for ex in user_examples.get("happy_path", []):
        cases.append(
            TestCase(
                id=f"tc_{idx:03d}",
                category="happy_path",
                input=ex.get("input", {}),
                expected=ex.get("expected_output", {}),
                match_strategy=MatchStrategy.schema,
                description="User-provided happy path example",
            )
        )
        idx += 1

    # Add a null input case
    empty_input = {f["name"]: None for f in spec.get("fields", [])}
    cases.append(
        TestCase(
            id=f"tc_{idx:03d}",
            category="null_empty",
            input=empty_input,
            expected={"error": True},
            match_strategy=MatchStrategy.contains,
            description="All fields null — should return error",
        )
    )
    idx += 1

    module_name = spec.get("module_name", "module")
    return TestSuite(module_name=module_name, total_cases=len(cases), cases=cases)


class BenchmarkGenerator:
    def __init__(self, llm: LLMClient):
        self._llm = llm

    async def generate(self, spec: dict, user_examples: dict) -> TestSuite:
        """Generate a full test suite from module spec + user examples."""
        module_name = spec.get("module_name", "module")

        user_prompt = (
            f"Module spec:\n{json.dumps(spec, indent=2)}\n\n"
            f"User-provided examples:\n{json.dumps(user_examples, indent=2)}\n\n"
            "Generate a comprehensive test suite as a JSON array."
        )

        try:
            content, _, _ = await self._llm.complete(
                system=GENERATOR_SYSTEM,
                user=user_prompt,
                max_tokens=4096,
            )
            raw_cases = json.loads(content)
        except Exception as exc:
            logger.warning("Benchmark LLM generation failed (%s), using fallback", exc)
            return _make_fallback_suite(spec, user_examples)

        cases = []
        for i, raw in enumerate(raw_cases):
            try:
                strategy_val = raw.get("match_strategy", "exact")
                try:
                    strategy = MatchStrategy(strategy_val)
                except ValueError:
                    strategy = MatchStrategy.exact

                cases.append(
                    TestCase(
                        id=raw.get("id", f"tc_{i+1:03d}"),
                        category=raw.get("category", "happy_path"),
                        input=raw.get("input", {}),
                        expected=raw.get("expected", {}),
                        match_strategy=strategy,
                        description=raw.get("description"),
                    )
                )
            except Exception as exc:
                logger.warning("Skipping malformed test case %d: %s", i, exc)

        if not cases:
            logger.warning("No valid cases parsed from LLM output, using fallback")
            return _make_fallback_suite(spec, user_examples)

        return TestSuite(module_name=module_name, total_cases=len(cases), cases=cases)
