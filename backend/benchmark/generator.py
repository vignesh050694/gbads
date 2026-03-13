import json
import logging
from typing import Any, Optional

from benchmark.cases import MatchStrategy, TestCase, TestSuite
from llm.client import LLMClient

logger = logging.getLogger(__name__)

METRIC_PLAN_SYSTEM = """You are a software QA architect. Given a module spec, generate a human-readable
metric approval plan BEFORE generating actual test cases. The user must approve this plan.

Return ONLY valid JSON matching the schema below:
{
  "metric": "Test case pass rate",
  "formula": "passed_cases / total_cases",
  "target": "1.0 (100%)",
  "planned_test_cases": {
    "happy_path": { "count": 3, "examples": ["..."] },
    "security": { "count": 4, "examples": ["..."] },
    "boundary": { "count": 3, "examples": ["..."] },
    "null_input": { "count": 3, "examples": ["..."] },
    "edge_case": { "count": 2, "examples": ["..."] }
  },
  "total_planned": 15,
  "real_infra_testing": false,
  "infra_services": [],
  "infra_note": "",
  "success_definition": "All N tests pass",
  "estimated_seconds_per_iteration": 30
}"""

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

    async def generate_metric_plan(
        self,
        module_spec: dict,
        user_examples: dict,
        repo_context: Optional[dict] = None,
        compose_result: Optional[dict] = None,
    ) -> dict:
        """Generate a human-readable metric plan for user approval BEFORE the loop starts."""
        services = (compose_result or {}).get("services", [])
        infra_note = (
            f"Tests will use real: {', '.join(services)}" if services else ""
        )

        user_msg = (
            f"Module spec:\n{json.dumps(module_spec, indent=2)}\n\n"
            f"Infrastructure services: {services or 'none (in-process only)'}\n"
            "Generate the metric approval plan JSON."
        )
        try:
            content, _, _ = await self._llm.complete(
                system=METRIC_PLAN_SYSTEM,
                user=user_msg,
                max_tokens=1024,
            )
            text = content.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            plan = json.loads(text)
        except Exception as exc:
            logger.warning("Metric plan LLM failed (%s), using fallback", exc)
            plan = {
                "metric": "Test case pass rate",
                "formula": "passed_cases / total_cases",
                "target": "1.0 (100%)",
                "planned_test_cases": {
                    "happy_path": {"count": 3, "examples": []},
                    "security": {"count": 2, "examples": []},
                    "boundary": {"count": 2, "examples": []},
                    "null_input": {"count": 2, "examples": []},
                    "edge_case": {"count": 1, "examples": []},
                },
                "total_planned": 10,
                "real_infra_testing": bool(services),
                "infra_services": services,
                "infra_note": infra_note,
                "success_definition": "All test cases pass",
                "estimated_seconds_per_iteration": 90 if services else 30,
            }

        # Ensure infra fields are set from compose_result
        plan["real_infra_testing"] = bool(services)
        plan["infra_services"] = services
        if infra_note:
            plan["infra_note"] = infra_note

        return plan

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
