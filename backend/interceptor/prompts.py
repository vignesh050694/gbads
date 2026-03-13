INTERCEPTOR_SYSTEM = """You are a software requirements analyst. Your job is to parse a natural language requirement and return a structured module specification as JSON.

Rules:
1. Return ONLY valid JSON — no prose, no markdown fences, no explanation.
2. Ask ZERO clarifying questions if the requirement is unambiguous.
3. Ask AT MOST 3 clarifying questions, and only architectural ones (e.g., "JWT vs session tokens?" not "what variable name to use?").
4. Never ask about implementation details — you decide those.
5. Include a confidence_score (0.0–1.0). If below 0.7 AND you have clarifying questions, surface them.
6. If clarifying answers are provided, use them to produce a final spec with confidence_score >= 0.9.

Output JSON schema:
{
  "module_name": "snake_case_name",
  "description": "One sentence description",
  "fields": [
    { "name": "field_name", "type": "string|integer|boolean|float|list|dict", "constraints": ["constraint1", "constraint2"] }
  ],
  "returns": [
    { "name": "return_field", "type": "string|integer|boolean|float|list|dict", "description": "what this is" }
  ],
  "error_cases": [
    { "condition": "description of when error occurs", "returns": "description of error response" }
  ],
  "clarifying_questions": [],
  "confidence_score": 0.95
}

The generated module must expose a function: def run(input_dict: dict) -> any
"""

INTERCEPTOR_USER_TEMPLATE = """Requirement:
{requirement}

{clarifications_section}

Parse this into a module spec JSON."""


def build_interceptor_prompt(
    requirement: str,
    clarifications: dict | None = None,
    repo_context: dict | None = None,
) -> str:
    if clarifications:
        lines = "\n".join(f"Q: {q}\nA: {a}" for q, a in clarifications.items())
        clarifications_section = f"Clarification answers:\n{lines}"
    else:
        clarifications_section = ""

    repo_section = ""
    if repo_context:
        stack = repo_context.get("detected_stack", {})
        tree = repo_context.get("file_tree", [])[:50]
        repo_section = (
            f"\nExisting codebase context:\n"
            f"Stack: {stack}\n"
            f"File tree (sample): {', '.join(tree)}\n"
        )

    return INTERCEPTOR_USER_TEMPLATE.format(
        requirement=requirement,
        clarifications_section=clarifications_section + repo_section,
    ).strip()
