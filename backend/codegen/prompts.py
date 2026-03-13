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

CODEGEN_SYSTEM_CODEBASE_AWARE = """You are modifying an existing codebase. Study the existing structure carefully and follow
its exact patterns — directory layout, import style, naming conventions, error handling.

Your response MUST start with:
TARGET_FILE: {relative/path/to/file.py}
---
{code here}

Choose the TARGET_FILE path to fit naturally into the existing structure.
If adding a new feature, follow where similar features live.
If modifying an existing file, use its exact current path.
The test runner will import your module as: from module import execute
So your TARGET_FILE must expose an execute(input_data: dict) -> dict function.

Additional rules:
1. Return code only — no prose outside the TARGET_FILE header.
2. Use the provided env vars for service connections.
3. Follow the existing error handling patterns in the codebase.
4. Study the failing test cases carefully and fix ALL of them.
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

CODEGEN_USER_TEMPLATE_CODEBASE = """Module spec:
{spec}

Test suite ({total_cases} cases):
{test_cases}

Iteration context:
{iteration_context}

Existing codebase:
File tree: {file_tree}

Key files:
{key_files}

Connection env vars: {connection_env_vars}

Generate the implementation. Start your response with TARGET_FILE: <path>
"""


def build_codegen_prompt(
    spec: dict,
    suite_dict: dict,
    iteration_context: dict,
    repo_context: dict | None = None,
    connection_env_vars: dict | None = None,
) -> str:
    import json

    module_name = spec.get("module_name", "module")
    total_cases = suite_dict.get("total_cases", 0)

    # Limit test case output to avoid blowing the context window
    cases = suite_dict.get("cases", [])
    cases_json = json.dumps(cases, indent=2)
    if len(cases_json) > 10000:
        cases_json = json.dumps(cases[:20], indent=2) + "\n... (truncated)"

    if repo_context:
        file_tree = repo_context.get("file_tree", [])[:100]
        key_files = repo_context.get("key_files", {})
        key_files_str = ""
        for path, content in list(key_files.items())[:10]:
            key_files_str += f"\n=== {path} ===\n{content[:500]}\n"

        return CODEGEN_USER_TEMPLATE_CODEBASE.format(
            spec=json.dumps(spec, indent=2),
            total_cases=total_cases,
            test_cases=cases_json,
            iteration_context=json.dumps(iteration_context, indent=2),
            file_tree=json.dumps(file_tree),
            key_files=key_files_str,
            connection_env_vars=json.dumps(connection_env_vars or {}),
        )

    return CODEGEN_USER_TEMPLATE.format(
        spec=json.dumps(spec, indent=2),
        total_cases=total_cases,
        test_cases=cases_json,
        iteration_context=json.dumps(iteration_context, indent=2),
        module_name=module_name,
    )
