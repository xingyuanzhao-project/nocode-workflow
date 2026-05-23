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

    async def execute(self, text: str, *, doc_id: Any = None) -> Dict[str, Any]:
        """Call the LLM and return all output fields as a dict.

        On error or parse failure, returns a dict with all output keys
        set to empty string and logs the error.
        """
        messages = [
            {"role": "system", "content": self._system_message},
            {"role": "user", "content": text},
        ]

        kwargs: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "response_format": self._response_format,
        }

        self.logger.info(
            "[LLM INPUT] model=%s doc_id=%s messages=%s",
            self.model_name, doc_id, json.dumps(messages, ensure_ascii=False),
        )

        try:
            if self.llm_semaphore:
                async with self.llm_semaphore:
                    response = await self.client.chat.completions.create(**kwargs)
            else:
                response = await self.client.chat.completions.create(**kwargs)

            raw_content = response.choices[0].message.content or ""

            self.logger.info(
                "[LLM OUTPUT] model=%s doc_id=%s content=%s",
                self.model_name, doc_id, raw_content,
            )

            parsed = json.loads(raw_content)
            if not isinstance(parsed, dict):
                raise ValueError(f"LLM returned non-object JSON: {type(parsed)}")

            result: Dict[str, Any] = {}
            for key in self._output_keys:
                result[key] = parsed.get(key, "")
            return result

        except Exception as exc:
            self.logger.error(
                "[LLM ERROR] model=%s doc_id=%s error=%s",
                self.model_name, doc_id, str(exc),
            )
            return {key: "" for key in self._output_keys}
