import json
import logging
from typing import Optional

from interceptor.prompts import INTERCEPTOR_SYSTEM, build_interceptor_prompt
from llm.client import LLMClient

logger = logging.getLogger(__name__)


class InterceptorAgent:
    def __init__(self, llm: LLMClient):
        self._llm = llm

    async def parse(
        self,
        requirement: str,
        clarifications: Optional[dict] = None,
    ) -> dict:
        """Parse a requirement into a module spec.

        Returns a dict with keys: module_name, description, fields, returns,
        error_cases, clarifying_questions, confidence_score.

        If confidence_score < 0.7 and clarifying_questions is non-empty,
        the caller should surface those questions to the user and call parse()
        again with answers.
        """
        user_prompt = build_interceptor_prompt(requirement, clarifications)

        content, prompt_tokens, completion_tokens = await self._llm.complete(
            system=INTERCEPTOR_SYSTEM,
            user=user_prompt,
            max_tokens=2048,
        )

        # Strip any accidental markdown fences
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            )

        try:
            spec = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.error("Interceptor returned invalid JSON: %s\nRaw: %s", exc, content)
            raise ValueError(f"Interceptor agent returned non-JSON response: {exc}") from exc

        # Ensure required fields exist
        spec.setdefault("module_name", "module")
        spec.setdefault("description", requirement[:100])
        spec.setdefault("fields", [])
        spec.setdefault("returns", [])
        spec.setdefault("error_cases", [])
        spec.setdefault("clarifying_questions", [])
        spec.setdefault("confidence_score", 0.9)

        logger.info(
            "Interceptor: module=%s confidence=%.2f questions=%d",
            spec["module_name"],
            spec["confidence_score"],
            len(spec["clarifying_questions"]),
        )
        return spec
