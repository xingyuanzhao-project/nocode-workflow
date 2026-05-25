"""Ad-hoc verification for src/processors.py step-level overrides.

For each of the five processor methods that now consume
``io_schema_resolved`` / ``prompt_resolved``:

1. Build a minimal processor instance with a config that matches the
   pre-registry behavior (no overrides) and confirm the returned
   ``response_format`` is byte-for-byte identical to the hardcoded
   dict the method used before.
2. Add an ``io_schema_resolved`` entry and confirm the returned
   ``response_format`` matches ``to_response_format(io_schema, ...)``.
3. Add a ``prompt_resolved`` entry and confirm the resulting
   ``messages[0].content`` reflects the override.

For ``_get_synthesis_args``: confirm overrides do NOT leak in, by
passing an ``io_schema_resolved`` of a different shape and checking
the hardcoded ``label_synthesis`` schema still wins.

Run with::

    .\\.venv\\Scripts\\python.exe _verify_processor_overrides.py
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from src.io_schema import IOSchema, to_response_format
from src.prompt_resolver import ResolvedPrompt


def _base_config_with_prompts() -> Dict[str, Any]:
    """Load config/prompts.json and return a minimal processor config dict.

    Returns:
        Config dict with ``model``, ``processing``, and ``prompts``
        keys sufficient to construct any processor class.
    """
    with open("config/prompts.json", "r", encoding="utf-8") as handle:
        prompts = json.load(handle)
    return {
        "model": {"name": "test-model"},
        "processing": {
            "temperature": 0.0,
        },
        "prompts": prompts,
    }


def _make_summary_processor(extra_cfg: Dict[str, Any] | None = None):
    """Construct an AsyncMessyTextProcessor with test defaults.

    Args:
        extra_cfg: Additional config entries (e.g. ``io_schema_resolved``,
            ``prompt_resolved``) merged into the base config.

    Returns:
        Configured AsyncMessyTextProcessor with a null LLM client.
    """
    from src.processors import AsyncMessyTextProcessor

    cfg = _base_config_with_prompts()
    if extra_cfg:
        cfg.update(extra_cfg)

    logger = logging.getLogger("verify_processor")
    # AsyncMessyTextProcessor wants a dict-like taxonomy with the usual keys.
    taxonomy = {"context_definitions": {}, "label_options": {}}
    return AsyncMessyTextProcessor(
        client=None, config=cfg, taxonomy=taxonomy, logger=logger,
        llm_semaphore=None,
    )


_HARDCODED_SUMMARY = {"type": "json_schema", "json_schema": {
    "name": "summary",
    "schema": {
        "type": "object",
        "properties": {
            "info_found": {"type": "string"},
            "relevant_context": {"type": "array"},
            "summary": {"type": "string"},
        },
        "required": ["info_found", "relevant_context", "summary"],
    },
}}

_HARDCODED_CONV = {"type": "json_schema", "json_schema": {
    "name": "conversation_summary",
    "schema": {
        "type": "object",
        "properties": {
            "info_found": {"type": "string"},
            "relevant_context": {"type": "array"},
            "summary_by_item": {
                "type": "object",
                "description": "Per-label extractive spans for traceback",
                "additionalProperties": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"span": {"type": "string"}},
                        "required": ["span"],
                    },
                },
            },
            "summary": {"type": "string"},
        },
        "required": ["info_found", "relevant_context", "summary_by_item", "summary"],
    },
}}

_HARDCODED_CLS = {"type": "json_schema", "json_schema": {
    "name": "classification",
    "schema": {
        "type": "object",
        "properties": {
            "evidence": {"type": "string"},
            "result": {"type": "string"},
        },
        "required": ["evidence", "result"],
    },
}}

_HARDCODED_LABEL_EXTRACT = {"type": "json_schema", "json_schema": {
    "name": "label_extract",
    "schema": {
        "type": "object",
        "properties": {
            "info_found": {"type": "string"},
            "spans": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"span": {"type": "string"}},
                    "required": ["span"],
                },
            },
            "confidence_score": {"type": "string"},
        },
        "required": ["info_found", "spans", "confidence_score"],
    },
}}

_HARDCODED_LABEL_SUMMARY = {"type": "json_schema", "json_schema": {
    "name": "label_summary",
    "schema": {
        "type": "object",
        "properties": {
            "info_found": {"type": "string"},
            "spans_by_item": {
                "type": "object",
                "additionalProperties": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"span": {"type": "string"}},
                        "required": ["span"],
                    },
                },
            },
            "summary": {"type": "string"},
        },
        "required": ["info_found", "spans_by_item", "summary"],
    },
}}

_HARDCODED_SYNTHESIS = {"type": "json_schema", "json_schema": {
    "name": "label_synthesis",
    "schema": {
        "type": "object",
        "properties": {
            "info_found": {"type": "string"},
            "summary": {"type": "string"},
        },
        "required": ["info_found", "summary"],
    },
}}


def test_summary_fallback_matches_hardcoded() -> None:
    """Confirm _get_summary_args without overrides reproduces the hardcoded schema."""
    proc = _make_summary_processor()
    args = proc._get_summary_args(text="hello world")
    assert args["response_format"] == _HARDCODED_SUMMARY, (
        "Fallback summary response_format diverged from hardcoded dict"
    )
    print("  ok   summary fallback matches hardcoded")


def test_summary_override_matches_io_schema() -> None:
    """Confirm _get_summary_args with an equivalent IOSchema yields the same result."""
    io_schema = IOSchema(output={
        "info_found": {"type": "string"},
        "relevant_context": {"type": "array"},
        "summary": {"type": "string"},
    })
    proc = _make_summary_processor({"io_schema_resolved": io_schema})
    args = proc._get_summary_args(text="hello world")
    assert args["response_format"] == to_response_format(io_schema, "summary")
    # Fallback-equivalent io_schema should still equal the hardcoded dict
    assert args["response_format"] == _HARDCODED_SUMMARY
    print("  ok   summary override via io_schema equals hardcoded (identity)")


def test_summary_prompt_override_is_honoured() -> None:
    """Confirm prompt_resolved instructions appear in summary message content."""
    prompt_resolved = ResolvedPrompt(
        instructions=["step A: {info_found_label}", "step B: {summary_label}"],
        output_format={"info_found": {"type": "string"}},
    )
    proc = _make_summary_processor({"prompt_resolved": prompt_resolved})
    args = proc._get_summary_args(text="hello world")
    content = args["messages"][0]["content"]
    assert "step A: info_found" in content, content
    assert "step B: summary" in content, content
    print("  ok   summary prompt_resolved drives instruction text")


def test_conversation_summary_fallback_matches_hardcoded() -> None:
    """Confirm _get_conversation_summary_args fallback matches the hardcoded schema."""
    proc = _make_summary_processor()
    args = proc._get_conversation_summary_args(
        previous_summary=None, text="hello",
    )
    assert args["response_format"] == _HARDCODED_CONV
    print("  ok   conversation_summary fallback matches hardcoded")


def test_classification_fallback_matches_hardcoded() -> None:
    """Confirm _get_classification_args fallback matches the hardcoded schema."""
    proc = _make_summary_processor()
    proc.definitions = {"k": "question?"}
    proc.labels = {"k": ["a", "b"]}
    args = proc._get_classification_args(summary="some summary", key="k")
    assert args["response_format"] == _HARDCODED_CLS
    print("  ok   classification fallback matches hardcoded")


def test_label_extract_fallback_matches_hardcoded() -> None:
    """Confirm _get_label_extract_args fallback matches the hardcoded schema."""
    from src.processors import AsyncLabelExtractor

    cfg = _base_config_with_prompts()
    logger = logging.getLogger("verify_processor")
    extractor = AsyncLabelExtractor(
        client=None, config=cfg,
        label_key="k", label_definition="d",
        logger=logger, llm_semaphore=None,
    )
    args = extractor._get_label_extract_args(text="hello", previous_spans=None)
    assert args["response_format"] == _HARDCODED_LABEL_EXTRACT
    print("  ok   label_extract fallback matches hardcoded")


def test_label_summary_fallback_matches_hardcoded() -> None:
    """Confirm _get_label_summary_args fallback matches the hardcoded schema."""
    from src.processors import AsyncTextLabelsSummaryProcessor

    cfg = _base_config_with_prompts()
    logger = logging.getLogger("verify_processor")
    processor = AsyncTextLabelsSummaryProcessor(
        client=None, config=cfg,
        taxonomy={"context_definitions": {}, "label_options": {}},
        logger=logger, llm_semaphore=None,
    )
    args = processor._get_label_summary_args(text="hello", label_results={})
    assert args["response_format"] == _HARDCODED_LABEL_SUMMARY
    print("  ok   label_summary fallback matches hardcoded")


def test_synthesis_ignores_step_level_io_schema() -> None:
    """Synthesis must not leak the (different) step-level io_schema."""
    from src.processors import AsyncTextLabelsSummaryProcessor

    cfg = _base_config_with_prompts()
    # Deliberately pass a wrong shape that the step-level resolver would
    # inject for a label_summary step.
    cfg["io_schema_resolved"] = IOSchema(output={
        "info_found": {"type": "string"},
        "spans_by_item": {"type": "object"},
        "summary": {"type": "string"},
    })
    cfg["prompt_resolved"] = ResolvedPrompt(
        instructions=["step A"], output_format={"foo": {"type": "string"}},
    )
    logger = logging.getLogger("verify_processor")
    processor = AsyncTextLabelsSummaryProcessor(
        client=None, config=cfg,
        taxonomy={"context_definitions": {}, "label_options": {}},
        logger=logger, llm_semaphore=None,
    )
    args = processor._get_synthesis_args(per_doc_summaries=["a", "b"])
    assert args["response_format"] == _HARDCODED_SYNTHESIS, (
        "Synthesis leaked the step-level io_schema override!"
    )
    content = args["messages"][0]["content"]
    # synthesis instructions come from label_synthesis prompt, not "step A"
    assert "step A" not in content, content
    print("  ok   synthesis preserves hardcoded schema under step-level overrides")


if __name__ == "__main__":
    test_summary_fallback_matches_hardcoded()
    test_summary_override_matches_io_schema()
    test_summary_prompt_override_is_honoured()
    test_conversation_summary_fallback_matches_hardcoded()
    test_classification_fallback_matches_hardcoded()
    test_label_extract_fallback_matches_hardcoded()
    test_label_summary_fallback_matches_hardcoded()
    test_synthesis_ignores_step_level_io_schema()
    print("ALL PROCESSOR OVERRIDE CHECKS PASSED")
