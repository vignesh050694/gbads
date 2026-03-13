CODEGEN_SYSTEM = """You are an expert Python developer. Your job is to implement a Python module that passes all provided test cases.

Rules:
1. Return ONLY the Python code for the implementation file — no prose, no markdown fences.
2. The module MUST expose a top-level function: def run(input_dict: dict) -> any
3. The code must be completely self-contained in ONE file.
4. You may only use Python standard library packages plus: json, re, hashlib, hmac, base64, datetime, uuid, typing.
5. Do NOT use any third-party packages (no requests, no jwt library, no bcrypt, etc.).
6. Handle ALL constraint validation internally in the run() function.
7. For JWT-like tokens, implement a simple HMAC-SHA256 based token — do NOT use PyJWT.
8. Return errors as dicts with an "error" key, NOT by raising exceptions (unless the test expects an exception).
9. Never modify the test runner — you only provide the implementation.
10. Study the failing test cases carefully and fix ALL of them.
"""

CODEGEN_USER_TEMPLATE = """Module spec:
{spec}

Test suite ({total_cases} cases):
{test_cases}

Iteration context:
{iteration_context}

Generate the complete implementation for {module_name}.py.
The file must define: def run(input_dict: dict) -> any
"""


def build_codegen_prompt(
    spec: dict,
    suite_dict: dict,
    iteration_context: dict,
) -> str:
    import json

    module_name = spec.get("module_name", "module")
    total_cases = suite_dict.get("total_cases", 0)

    # Limit test case output to avoid blowing the context window
    cases = suite_dict.get("cases", [])
    cases_json = json.dumps(cases, indent=2)
    # Truncate if too long (rough guard)
    if len(cases_json) > 10000:
        cases_json = json.dumps(cases[:20], indent=2) + "\n... (truncated)"

    return CODEGEN_USER_TEMPLATE.format(
        spec=json.dumps(spec, indent=2),
        total_cases=total_cases,
        test_cases=cases_json,
        iteration_context=json.dumps(iteration_context, indent=2),
        module_name=module_name,
    )
