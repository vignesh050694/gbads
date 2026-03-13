import logging
import re

from benchmark.cases import TestSuite
from codegen.prompts import CODEGEN_SYSTEM, build_codegen_prompt
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
    ) -> str:
        """Generate Python implementation code for the given spec and test suite.

        Returns a raw Python source string (single file, no markdown fences).
        """
        suite_dict = suite.to_runner_dict()
        user_prompt = build_codegen_prompt(spec, suite_dict, iteration_context)

        content, prompt_tokens, completion_tokens = await self._llm.complete(
            system=CODEGEN_SYSTEM,
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

    @staticmethod
    def _strip_fences(content: str) -> str:
        """Remove markdown code fences if present."""
        content = content.strip()
        # Remove ```python ... ``` or ``` ... ```
        fence_pattern = re.compile(r"^```[a-z]*\n(.*?)\n?```$", re.DOTALL)
        m = fence_pattern.match(content)
        if m:
            return m.group(1).strip()
        # Try removing just leading/trailing fence lines
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
