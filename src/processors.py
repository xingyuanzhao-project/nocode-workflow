"""Generic LLM processor for the flow runner.

A single class that takes user-configured io_schema and prompt instructions,
calls the LLM, and returns ALL response fields as a dict. No hardcoded field
names, no taxonomy, no conversation state.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from src.format_adapter import adapt_request_kwargs, normalize_llm_response
from src.io_schema import IOSchema, to_response_format


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MULTI_SPACE_RE = re.compile(r"[ \t]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


class GenericProcessor:
    """Executes a single LLM call per invocation using the user's schema.

    The caller (flow_builder._run_generic) is responsible for concurrency
    at the row level. This class owns the LLM semaphore for API-level
    throttling.
    """

    def __init__(
        self,
        client: AsyncOpenAI,
        io_schema: IOSchema,
        instructions: List[str],
        model_name: str,
        logger: logging.Logger,
        *,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        llm_semaphore: Optional[asyncio.Semaphore] = None,
    ) -> None:
        self.client = client
        self.io_schema = io_schema
        self.instructions = instructions
        self.model_name = model_name
        self.logger = logger
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.llm_semaphore = llm_semaphore

        self._output_keys: List[str] = list(io_schema.output.keys())
        self._response_format = to_response_format(io_schema, "processor_output")
        self._system_message = "\n".join(instructions)

    def clean_text(self, raw: str) -> str:
        """Strip HTML tags, fix encoding artifacts, collapse whitespace."""
        text = _HTML_TAG_RE.sub(" ", raw)
        text = text.replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
        text = _MULTI_SPACE_RE.sub(" ", text)
        text = _MULTI_NEWLINE_RE.sub("\n\n", text)
        return text.strip()

    async def execute(
        self, input_fields: Dict[str, str], *, row_index: int = 0,
    ) -> Dict[str, Any]:
        """Call the LLM and return all output fields as a dict.

        Args:
            input_fields: Column-name → cleaned-value mapping for this row.
            row_index: Positional row index for logging.

        On error or parse failure, returns a dict with all output keys
        set to empty string and logs the error.
        """
        if len(input_fields) == 1:
            user_content = next(iter(input_fields.values()))
        else:
            user_content = "\n\n".join(
                f"[{field}]: {value}" for field, value in input_fields.items()
            )

        messages = [
            {"role": "system", "content": self._system_message},
            {"role": "user", "content": user_content},
        ]

        kwargs: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "response_format": self._response_format,
        }

        kwargs = adapt_request_kwargs(self.model_name, kwargs)

        self.logger.info(
            "[LLM INPUT] model=%s row=%d messages=%s",
            self.model_name, row_index, json.dumps(messages, ensure_ascii=False),
        )

        try:
            if self.llm_semaphore:
                async with self.llm_semaphore:
                    response = await self.client.chat.completions.create(**kwargs)
            else:
                response = await self.client.chat.completions.create(**kwargs)

            raw_content = response.choices[0].message.content or ""

            self.logger.info(
                "[LLM OUTPUT] model=%s row=%d content=%s",
                self.model_name, row_index, raw_content,
            )

            result, success = normalize_llm_response(raw_content, self._output_keys)
            if not success:
                self.logger.warning(
                    "[LLM PARSE] model=%s row=%d normalization used fallback",
                    self.model_name, row_index,
                )
            return result

        except Exception as exc:
            self.logger.error(
                "[LLM ERROR] model=%s row=%d error=%s",
                self.model_name, row_index, str(exc),
            )
            return {key: "" for key in self._output_keys}
