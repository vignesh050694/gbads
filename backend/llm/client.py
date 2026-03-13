import time
import logging
from typing import Optional

import anthropic
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from config import get_settings

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self):
        settings = get_settings()
        self._client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key
        )
        self._model = settings.model_id
        self._max_tokens = settings.max_tokens_per_call

    @retry(
        retry=retry_if_exception_type(
            (anthropic.RateLimitError, anthropic.InternalServerError)
        ),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def complete(
        self,
        system: str,
        user: str,
        max_tokens: Optional[int] = None,
    ) -> tuple[str, int, int]:
        """Send a message and return (content, prompt_tokens, completion_tokens)."""
        start = time.monotonic()
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens or self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        duration_ms = int((time.monotonic() - start) * 1000)

        content = response.content[0].text
        prompt_tokens = response.usage.input_tokens
        completion_tokens = response.usage.output_tokens

        logger.info(
            "LLM call: prompt=%d tokens, completion=%d tokens, duration=%dms",
            prompt_tokens,
            completion_tokens,
            duration_ms,
        )
        return content, prompt_tokens, completion_tokens

    @retry(
        retry=retry_if_exception_type(
            (anthropic.RateLimitError, anthropic.InternalServerError)
        ),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def complete_with_tools(
        self,
        system: str,
        messages: list,
        tools: list,
        max_tokens: Optional[int] = None,
    ) -> tuple:
        """
        Send a message with tool definitions.
        Returns (Message, prompt_tokens, completion_tokens).
        The caller manages the agentic loop (handling tool_use blocks and sending results).
        """
        start = time.monotonic()
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens or self._max_tokens,
            system=system,
            messages=messages,
            tools=tools,
        )
        duration_ms = int((time.monotonic() - start) * 1000)

        prompt_tokens = response.usage.input_tokens
        completion_tokens = response.usage.output_tokens

        logger.info(
            "LLM tool call: stop_reason=%s prompt=%d completion=%d duration=%dms",
            response.stop_reason,
            prompt_tokens,
            completion_tokens,
            duration_ms,
        )
        return response, prompt_tokens, completion_tokens
