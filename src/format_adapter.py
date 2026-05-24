"""Request normalization and output parsing for LLM calls.

- :func:`normalize_request_kwargs` — normalizes the ``response_format``
  parameter shape for providers whose OpenAI-compatible endpoints accept
  structured output but with a different parameter form. Google/Gemini's
  endpoint supports ``{"type": "json_object"}`` but does not reliably
  handle the full ``{"type": "json_schema", "json_schema": {...}}`` form;
  the normalizer converts it to json_object mode + schema in prompt.

- :func:`normalize_llm_response` — extracts a valid JSON dict from the
  raw LLM response string. Handles markdown code fences and embedded JSON.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple


_JSON_FENCE_RE = re.compile(
    r"```(?:json)?\s*\n?(.*?)\n?\s*```",
    re.DOTALL,
)

_JSON_OBJECT_RE = re.compile(
    r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}",
    re.DOTALL,
)


def normalize_request_kwargs(
    provider: str,
    kwargs: Dict[str, Any],
) -> Dict[str, Any]:
    """Normalize the response_format parameter shape for the target provider.

    Most providers (openai, openrouter, vllm, ollama, llama_cpp, claude)
    accept the full ``{"type": "json_schema", ...}`` form unchanged.

    Google/Gemini's OpenAI-compatible endpoint accepts structured output
    via ``{"type": "json_object"}`` mode. The full json_schema dict causes
    truncated responses. This normalizer converts the parameter and moves
    the schema into the system message.

    This is format normalization, not capability gating — all providers
    receive response_format; only the parameter shape differs.
    """
    if provider != "google":
        return kwargs

    response_format = kwargs.get("response_format")
    if response_format is None:
        return kwargs

    if not isinstance(response_format, dict):
        return kwargs

    if response_format.get("type") != "json_schema":
        return kwargs

    adapted = dict(kwargs)
    adapted["response_format"] = {"type": "json_object"}

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


def _build_schema_instruction(response_format: Dict[str, Any]) -> str:
    """Convert a response_format json_schema dict into prompt instructions."""
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


def normalize_llm_response(
    raw_content: str,
    expected_keys: List[str],
) -> Tuple[Dict[str, Any], bool]:
    """Extract a valid JSON dict from raw LLM response content.

    Strategies tried in order:
    1. Direct JSON parse
    2. JSON inside markdown code fences
    3. JSON object embedded in free text

    If none succeed, returns empty values and success=False.

    Args:
        raw_content: The raw string from response.choices[0].message.content.
        expected_keys: The list of output field names we expect.

    Returns:
        A tuple of (parsed_dict, success). parsed_dict has all expected_keys
        (missing ones default to ""). success is True only if valid JSON was
        fully parsed.
    """
    empty_result = {k: "" for k in expected_keys}

    if not raw_content or not raw_content.strip():
        return empty_result, False

    text = raw_content.strip()

    parsed = _try_parse_json(text)
    if parsed is not None:
        return _extract_keys(parsed, expected_keys), True

    fence_match = _JSON_FENCE_RE.search(text)
    if fence_match:
        inner = fence_match.group(1).strip()
        parsed = _try_parse_json(inner)
        if parsed is not None:
            return _extract_keys(parsed, expected_keys), True

    obj_match = _JSON_OBJECT_RE.search(text)
    if obj_match:
        parsed = _try_parse_json(obj_match.group(0))
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
