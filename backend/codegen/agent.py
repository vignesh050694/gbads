import logging
import re
from typing import Optional

from benchmark.cases import TestSuite
from codegen.prompts import (
    CODEGEN_SYSTEM,
    CODEGEN_SYSTEM_CODEBASE_AWARE,
    build_codegen_prompt,
)
from llm.client import LLMClient

logger = logging.getLogger(__name__)


class CodegenAgent:
    def __init__(self, llm: LLMClient):
        self._llm = llm

    async def generate(
        self,
        spec: dict,
        suite: TestSuite,
        iteration_context: dict,
        repo_context: Optional[dict] = None,
        connection_env_vars: Optional[dict] = None,
    ) -> str:
        """Generate Python implementation code.

        Returns raw Python source string (single file, no markdown fences).
        When repo_context is provided, may return a TARGET_FILE-prefixed response.
        """
        suite_dict = suite.to_runner_dict()
        system = CODEGEN_SYSTEM_CODEBASE_AWARE if repo_context else CODEGEN_SYSTEM
        user_prompt = build_codegen_prompt(
            spec, suite_dict, iteration_context,
            repo_context=repo_context,
            connection_env_vars=connection_env_vars,
        )

        content, prompt_tokens, completion_tokens = await self._llm.complete(
            system=system,
            user=user_prompt,
            max_tokens=4096,
        )

        code = self._strip_fences(content)

        logger.info(
            "Codegen: iteration=%d prompt=%d tokens completion=%d tokens",
            iteration_context.get("iteration_number", 0),
            prompt_tokens,
            completion_tokens,
        )
        return code

    async def generate_with_target(
        self,
        spec: dict,
        suite: TestSuite,
        iteration_context: dict,
        repo_context: Optional[dict] = None,
        connection_env_vars: Optional[dict] = None,
    ) -> tuple[str, str, int]:
        """Generate code and extract TARGET_FILE header.

        Returns (target_file_path, code_string, tokens_used).
        Falls back to module_name.py if no TARGET_FILE header found.
        """
        suite_dict = suite.to_runner_dict()
        system = CODEGEN_SYSTEM_CODEBASE_AWARE if repo_context else CODEGEN_SYSTEM
        user_prompt = build_codegen_prompt(
            spec, suite_dict, iteration_context,
            repo_context=repo_context,
            connection_env_vars=connection_env_vars,
        )

        content, prompt_tokens, completion_tokens = await self._llm.complete(
            system=system,
            user=user_prompt,
            max_tokens=4096,
        )
        tokens_used = prompt_tokens + completion_tokens

        # Parse TARGET_FILE header
        target_file = None
        code = self._strip_fences(content)
        target_match = re.match(r"TARGET_FILE:\s*(.+?)\s*\n---\s*\n", code, re.DOTALL)
        if target_match:
            target_file = target_match.group(1).strip()
            code = code[target_match.end():]
        else:
            module_name = spec.get("module_name", "module")
            target_file = f"{module_name}.py"

        logger.info("Codegen: target=%s tokens=%d", target_file, tokens_used)
        return target_file, code, tokens_used

    @staticmethod
    def _strip_fences(content: str) -> str:
        """Remove markdown code fences if present."""
        content = content.strip()
        fence_pattern = re.compile(r"^```[a-z]*\n(.*?)\n?```$", re.DOTALL)
        m = fence_pattern.match(content)
        if m:
            return m.group(1).strip()
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
