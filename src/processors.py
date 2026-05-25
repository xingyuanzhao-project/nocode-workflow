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

from src.format_adapter import normalize_llm_response, normalize_request_kwargs
from src.io_schema import IOSchema, to_response_format


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MULTI_SPACE_RE = re.compile(r"[ \t]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


class ParseWarning(Exception):
    """Raised when LLM output could not be parsed into valid JSON.

    The row is still returned with empty values, but the caller should
    emit a visible warning rather than silently marking success.
    """

    def __init__(self, row_index: int, model_name: str, raw_content: str) -> None:
        self.row_index = row_index
        self.raw_content_preview = raw_content[:200]
        super().__init__(
            f"Row {row_index}: model={model_name} returned unparseable response"
        )


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
        system_message: str,
        model_name: str,
        provider: str,
        logger: logging.Logger,
        *,
        temperature: float = 0.0,
        llm_semaphore: Optional[asyncio.Semaphore] = None,
    ) -> None:
        self.client = client
        self.io_schema = io_schema
        self.model_name = model_name
        self.provider = provider
        self.logger = logger
        self.temperature = temperature
        self.llm_semaphore = llm_semaphore

        self._output_keys: List[str] = list(io_schema.output.keys())
        self._response_format = to_response_format(io_schema, "processor_output")
        self._system_message = system_message

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

        Raises:
            ParseWarning: If the LLM response cannot be parsed as valid JSON.
            Exception: If the LLM API call itself fails.
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
            "response_format": self._response_format,
        }
        kwargs = normalize_request_kwargs(self.provider, kwargs)

        self.logger.info(
            "[LLM INPUT] model=%s row=%d messages=%s",
            self.model_name, row_index,
            json.dumps(kwargs["messages"], ensure_ascii=False),
        )

        try:
            if self.llm_semaphore:
                async with self.llm_semaphore:
                    response = await self.client.chat.completions.create(**kwargs)
            else:
                response = await self.client.chat.completions.create(**kwargs)

            raw_content = response.choices[0].message.content or ""
            finish_reason = response.choices[0].finish_reason or "unknown"

            self.logger.info(
                "[LLM OUTPUT] model=%s row=%d finish_reason=%s content=%s",
                self.model_name, row_index, finish_reason, raw_content,
            )

            result, success = normalize_llm_response(raw_content, self._output_keys)
            if not success:
                self.logger.warning(
                    "[LLM PARSE] model=%s row=%d failed to parse response",
                    self.model_name, row_index,
                )
                raise ParseWarning(row_index, self.model_name, raw_content)
            return result

        except ParseWarning:
            raise
        except Exception as exc:
            self.logger.error(
                "[LLM ERROR] model=%s row=%d error=%s",
                self.model_name, row_index, str(exc),
            )
            raise
