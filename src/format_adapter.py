"""Input request adaptation and output response normalization for LLM calls.

Different models/providers accept different parameter shapes for structured
output. This module provides two functions:

- :func:`adapt_request_kwargs` — modifies the request kwargs dict before
  sending to the LLM. For models that don't reliably enforce
  ``response_format: {"type": "json_schema", ...}``, it removes that
  parameter and embeds the schema instructions into the system message.

- :func:`normalize_llm_response` — extracts a valid JSON dict from the
  raw LLM response string. Handles markdown code fences, partial JSON,
  and free-text responses where the JSON is embedded.

Evidence basis for model classification:
- google/gemini-* via OpenRouter: returns truncated JSON when
  response_format is set (worker.log 2026-05-23 run 1e87f7a1...).
- meta-llama/llama-3-8b-instruct via OpenRouter: works correctly with
  response_format (same log, second run).
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple


_MODELS_RESPONSE_FORMAT_WORKS: List[re.Pattern] = [
    re.compile(r"^openai/"),
    re.compile(r"^gpt-"),
]
"""Model name patterns where response_format json_schema is reliably enforced.

Only these models get the native response_format parameter. All others
use the schema-in-prompt fallback, which is safer and more portable."""


_JSON_FENCE_RE = re.compile(
    r"```(?:json)?\s*\n?(.*?)\n?\s*```",
    re.DOTALL,
)
"""Matches markdown code fences (with or without 'json' tag)."""

_JSON_OBJECT_RE = re.compile(
    r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}",
    re.DOTALL,
)
"""Greedy match for a JSON-like object (supports one level of nesting)."""


def model_needs_prompt_schema(model_name: str) -> bool:
    """Return True if the model needs schema embedded in prompt (no response_format).

    Uses a whitelist approach: only explicitly known-good models get
    response_format. Everything else uses schema-in-prompt.
    """
    for pattern in _MODELS_RESPONSE_FORMAT_WORKS:
        if pattern.search(model_name):
            return False
    return True


def _build_schema_instruction(response_format: Dict[str, Any]) -> str:
    """Convert a response_format dict into a plain-text instruction for the prompt."""
    json_schema = response_format.get("json_schema", {})
    schema = json_schema.get("schema", {})
    properties = schema.get("properties", {})
    required = schema.get("required", [])

    lines = [
        "You MUST respond with ONLY a valid JSON object (no markdown, no explanation).",
        "The JSON object must have exactly these fields:",
    ]
    for field_name, field_spec in properties.items():
        field_type = field_spec.get("type", "string")
        req_marker = " (required)" if field_name in required else ""
        lines.append(f'  - "{field_name}": {field_type}{req_marker}')

    lines.append("")
    lines.append("Example format:")
    example = {}
    for field_name, field_spec in properties.items():
        ftype = field_spec.get("type", "string")
        if ftype == "array":
            example[field_name] = []
        elif ftype == "object":
            example[field_name] = {}
        else:
            example[field_name] = "..."
    lines.append(json.dumps(example, indent=2))

    return "\n".join(lines)


def adapt_request_kwargs(
    model_name: str,
    kwargs: Dict[str, Any],
) -> Dict[str, Any]:
    """Adapt the chat.completions.create kwargs for model-specific requirements.

    For models that reliably support response_format (OpenAI, Llama via
    OpenRouter, vLLM, etc.), the kwargs are returned unchanged.

    For models that DON'T reliably enforce response_format (Gemini,
    Anthropic via OpenRouter), the response_format is removed and a
    schema instruction is prepended to the system message.

    Args:
        model_name: The model identifier (e.g. "google/gemini-2.0-flash-001").
        kwargs: The original kwargs dict for chat.completions.create.

    Returns:
        A (possibly modified) kwargs dict ready to send.
    """
    if not model_needs_prompt_schema(model_name):
        return kwargs

    response_format = kwargs.get("response_format")
    if response_format is None:
        return kwargs

    adapted = dict(kwargs)
    del adapted["response_format"]

    schema_instruction = _build_schema_instruction(response_format)

    messages = list(adapted.get("messages", []))
    if messages and messages[0].get("role") == "system":
        original_system = messages[0]["content"]
        messages[0] = {
            "role": "system",
            "content": f"{original_system}\n\n{schema_instruction}",
        }
    else:
        messages.insert(0, {"role": "system", "content": schema_instruction})

    adapted["messages"] = messages
    return adapted


def normalize_llm_response(
    raw_content: str,
    expected_keys: List[str],
) -> Tuple[Dict[str, Any], bool]:
    """Extract a valid JSON dict from raw LLM response content.

    Handles multiple response shapes:
    1. Clean JSON (the happy path when response_format works)
    2. JSON wrapped in markdown code fences (```json ... ```)
    3. JSON embedded in free-text explanation
    4. Partial/truncated JSON (best-effort extraction)

    Args:
        raw_content: The raw string from response.choices[0].message.content.
        expected_keys: The list of output field names we expect.

    Returns:
        A tuple of (parsed_dict, success). parsed_dict has all expected_keys
        (missing ones default to ""). success is True if parsing succeeded.
    """
    empty_result = {k: "" for k in expected_keys}

    if not raw_content or not raw_content.strip():
        return empty_result, False

    text = raw_content.strip()

    # Strategy 1: Direct JSON parse
    parsed = _try_parse_json(text)
    if parsed is not None:
        return _extract_keys(parsed, expected_keys), True

    # Strategy 2: Strip markdown code fences
    fence_match = _JSON_FENCE_RE.search(text)
    if fence_match:
        inner = fence_match.group(1).strip()
        parsed = _try_parse_json(inner)
        if parsed is not None:
            return _extract_keys(parsed, expected_keys), True

    # Strategy 3: Find JSON object in free text
    obj_match = _JSON_OBJECT_RE.search(text)
    if obj_match:
        parsed = _try_parse_json(obj_match.group(0))
        if parsed is not None:
            return _extract_keys(parsed, expected_keys), True

    # Strategy 4: Try to repair truncated JSON
    parsed = _try_repair_truncated(text, expected_keys)
    if parsed is not None:
        return _extract_keys(parsed, expected_keys), True

    return empty_result, False


def _try_parse_json(text: str) -> Any:
    """Attempt JSON parse, return None on failure."""
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _extract_keys(parsed: Dict[str, Any], expected_keys: List[str]) -> Dict[str, Any]:
    """Extract expected keys from parsed dict, defaulting missing to empty string."""
    return {k: parsed.get(k, "") for k in expected_keys}


def _try_repair_truncated(text: str, expected_keys: List[str]) -> Any:
    """Try to repair truncated JSON by closing open strings/braces."""
    # Find the start of JSON
    start = text.find("{")
    if start == -1:
        return None

    fragment = text[start:]

    # Count unclosed braces and try to close them
    for suffix in ['"}', '"}}', '"]}', '"]}}']:
        candidate = fragment + suffix
        parsed = _try_parse_json(candidate)
        if parsed is not None:
            return parsed

    # More aggressive: try adding closing for each expected pattern
    # If we see at least one complete key-value, extract what we can
    result = {}
    for key in expected_keys:
        pattern = re.compile(
            rf'"{re.escape(key)}"\s*:\s*("(?:[^"\\]|\\.)*"|'
            rf'\[.*?\]|\{{.*?\}}|null|true|false|\d+(?:\.\d+)?)',
            re.DOTALL,
        )
        match = pattern.search(fragment)
        if match:
            val_str = match.group(1)
            try:
                result[key] = json.loads(val_str)
            except (json.JSONDecodeError, ValueError):
                result[key] = val_str.strip('"')

    if result:
        return result
    return None
