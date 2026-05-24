"""Conversion between YAML-declared I/O schemas and OpenAI response formats.

A user-declared ``io_schema`` block in a flow YAML file is a structural
contract: it names the input fields a processor step reads and the output
fields the LLM is asked to return. This module holds the single canonical
translation from that YAML shape into the two artefacts the runtime needs:

1. The OpenAI ``chat.completions.create`` ``response_format`` dict (a
   JSON Schema envelope) used to enforce structured output on the
   provider side.
2. A short human-readable text rendering of the output contract that can
   be embedded in the prompt body so the model sees the same shape
   documented in YAML.

Contents and relationships
--------------------------

- :class:`IOSchema` — validated Pydantic model matching the YAML block.
  Its :attr:`IOSchema.output` dict is shaped like JSON Schema property
  specs (``{field_name: {"type": ...}}``); this is the same shape used
  inside :mod:`src.processors`'s currently-hardcoded response formats.
- :func:`to_response_format` — converts an :class:`IOSchema` into the
  ``{"type": "json_schema", "json_schema": {...}}`` dict consumed by
  ``AsyncOpenAI.chat.completions.create``.
- :func:`to_prompt_output_format_text` — converts the output half of an
  :class:`IOSchema` into a JSON string suitable for embedding in the
  prompt body.

How the rest of the system uses this module
-------------------------------------------

:mod:`src.flow_loader` declares an ``io_schema`` field on
:class:`src.flow_loader.StepConfig` typed as ``Optional[IOSchema]`` so
users can override the schema per step. :mod:`src.flow_builder` resolves
the effective ``io_schema`` (step override → registry default →
``None``) and injects it into each processor's runtime config under the
key ``io_schema_resolved``. Each ``_get_*_args`` method in
:mod:`src.processors` reads that key and, when present, calls
:func:`to_response_format` instead of the method's historical hardcoded
dict.

Invariants enforced by this module
----------------------------------

- Every output field becomes a required JSON Schema property. The
  ``required`` list is always exactly ``list(io_schema.output.keys())``
  in declaration order.
- The ``schema.type`` field is always ``"object"``. Nested arrays and
  nested objects are expressed inside each property spec, not at the
  top level.
- The module does no I/O and has no side effects; it is a pure converter
  and can be imported from any other module without creating a cycle.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class IOSchema(BaseModel):
    """Validated YAML-side structural contract for one processor step.

    Attributes:
        input (Dict[str, Any]): Input-field descriptor dict keyed by
            field name. Informational for now; consumed by the future
            GUI edge validator. Never flows into the LLM request.
        output (Dict[str, Any]): Output-field descriptor dict keyed by
            field name. Each value is a JSON Schema property spec (for
            example ``{"type": "string"}`` or
            ``{"type": "array", "items": {...}}``). :func:`to_response_format`
            copies this dict verbatim into the generated JSON Schema.
        required_output (List[str]): Subset of output field names that
            must appear in every LLM response. When non-empty,
            :func:`to_response_format` uses this list as the JSON Schema
            ``required`` array instead of defaulting to all output keys.
    """

    model_config = ConfigDict(extra="forbid")

    input: Dict[str, Any] = Field(default_factory=dict)
    output: Dict[str, Any] = Field(default_factory=dict)
    required_output: List[str] = Field(default_factory=list)


def to_response_format(
    io_schema: IOSchema,
    schema_name: str,
) -> Dict[str, Any]:
    """Convert an :class:`IOSchema` into an OpenAI ``response_format`` dict.

    The returned dict is shaped exactly as the ``response_format``
    argument of ``AsyncOpenAI.chat.completions.create``. Every output
    field becomes a required property in the generated JSON Schema in
    declaration order.

    Args:
        io_schema (IOSchema): The validated I/O schema block.
        schema_name (str): Value written to
            ``response_format["json_schema"]["name"]``. Used by the
            model provider for logging and by downstream code that
            groups results by task.

    Returns:
        Dict[str, Any]: The OpenAI ``response_format`` dict.

    Example:
        Verify the converter output matches the hardcoded ``summary``
        response format in :mod:`src.processors` byte-for-byte:

        >>> summary_schema = IOSchema(output={
        ...     "info_found": {"type": "string"},
        ...     "relevant_context": {"type": "array"},
        ...     "summary": {"type": "string"},
        ... })
        >>> expected_summary = {"type": "json_schema", "json_schema": {
        ...     "name": "summary",
        ...     "schema": {
        ...         "type": "object",
        ...         "properties": {
        ...             "info_found": {"type": "string"},
        ...             "relevant_context": {"type": "array"},
        ...             "summary": {"type": "string"},
        ...         },
        ...         "required": ["info_found", "relevant_context", "summary"],
        ...     },
        ... }}
        >>> to_response_format(summary_schema, "summary") == expected_summary
        True

        Verify the converter output matches the hardcoded
        ``conversation_summary`` response format byte-for-byte:

        >>> conversation_schema = IOSchema(output={
        ...     "info_found": {"type": "string"},
        ...     "relevant_context": {"type": "array"},
        ...     "summary_by_item": {
        ...         "type": "object",
        ...         "description": "Per-label extractive spans for traceback",
        ...         "additionalProperties": {
        ...             "type": "array",
        ...             "items": {
        ...                 "type": "object",
        ...                 "properties": {"span": {"type": "string"}},
        ...                 "required": ["span"],
        ...             },
        ...         },
        ...     },
        ...     "summary": {"type": "string"},
        ... })
        >>> expected_conv = {"type": "json_schema", "json_schema": {
        ...     "name": "conversation_summary",
        ...     "schema": {
        ...         "type": "object",
        ...         "properties": {
        ...             "info_found": {"type": "string"},
        ...             "relevant_context": {"type": "array"},
        ...             "summary_by_item": {
        ...                 "type": "object",
        ...                 "description": "Per-label extractive spans for traceback",
        ...                 "additionalProperties": {
        ...                     "type": "array",
        ...                     "items": {
        ...                         "type": "object",
        ...                         "properties": {"span": {"type": "string"}},
        ...                         "required": ["span"],
        ...                     },
        ...                 },
        ...             },
        ...             "summary": {"type": "string"},
        ...         },
        ...         "required": [
        ...             "info_found", "relevant_context",
        ...             "summary_by_item", "summary",
        ...         ],
        ...     },
        ... }}
        >>> to_response_format(conversation_schema, "conversation_summary") == expected_conv
        True

        Verify the converter output matches the hardcoded
        ``classification`` response format byte-for-byte:

        >>> classification_schema = IOSchema(output={
        ...     "evidence": {"type": "string"},
        ...     "result": {"type": "string"},
        ... })
        >>> expected_cls = {"type": "json_schema", "json_schema": {
        ...     "name": "classification",
        ...     "schema": {
        ...         "type": "object",
        ...         "properties": {
        ...             "evidence": {"type": "string"},
        ...             "result": {"type": "string"},
        ...         },
        ...         "required": ["evidence", "result"],
        ...     },
        ... }}
        >>> to_response_format(classification_schema, "classification") == expected_cls
        True

        Verify the converter output matches the hardcoded
        ``label_extract`` response format byte-for-byte:

        >>> label_extract_schema = IOSchema(output={
        ...     "info_found": {"type": "string"},
        ...     "spans": {
        ...         "type": "array",
        ...         "items": {
        ...             "type": "object",
        ...             "properties": {"span": {"type": "string"}},
        ...             "required": ["span"],
        ...         },
        ...     },
        ...     "confidence_score": {"type": "string"},
        ... })
        >>> expected_lx = {"type": "json_schema", "json_schema": {
        ...     "name": "label_extract",
        ...     "schema": {
        ...         "type": "object",
        ...         "properties": {
        ...             "info_found": {"type": "string"},
        ...             "spans": {
        ...                 "type": "array",
        ...                 "items": {
        ...                     "type": "object",
        ...                     "properties": {"span": {"type": "string"}},
        ...                     "required": ["span"],
        ...                 },
        ...             },
        ...             "confidence_score": {"type": "string"},
        ...         },
        ...         "required": ["info_found", "spans", "confidence_score"],
        ...     },
        ... }}
        >>> to_response_format(label_extract_schema, "label_extract") == expected_lx
        True

        Verify the converter output matches the hardcoded
        ``label_summary`` response format byte-for-byte:

        >>> label_summary_schema = IOSchema(output={
        ...     "info_found": {"type": "string"},
        ...     "spans_by_item": {
        ...         "type": "object",
        ...         "additionalProperties": {
        ...             "type": "array",
        ...             "items": {
        ...                 "type": "object",
        ...                 "properties": {"span": {"type": "string"}},
        ...                 "required": ["span"],
        ...             },
        ...         },
        ...     },
        ...     "summary": {"type": "string"},
        ... })
        >>> expected_ls = {"type": "json_schema", "json_schema": {
        ...     "name": "label_summary",
        ...     "schema": {
        ...         "type": "object",
        ...         "properties": {
        ...             "info_found": {"type": "string"},
        ...             "spans_by_item": {
        ...                 "type": "object",
        ...                 "additionalProperties": {
        ...                     "type": "array",
        ...                     "items": {
        ...                         "type": "object",
        ...                         "properties": {"span": {"type": "string"}},
        ...                         "required": ["span"],
        ...                     },
        ...                 },
        ...             },
        ...             "summary": {"type": "string"},
        ...         },
        ...         "required": ["info_found", "spans_by_item", "summary"],
        ...     },
        ... }}
        >>> to_response_format(label_summary_schema, "label_summary") == expected_ls
        True

        Verify the converter output matches the hardcoded
        ``label_synthesis`` response format byte-for-byte:

        >>> label_synthesis_schema = IOSchema(output={
        ...     "info_found": {"type": "string"},
        ...     "summary": {"type": "string"},
        ... })
        >>> expected_lsn = {"type": "json_schema", "json_schema": {
        ...     "name": "label_synthesis",
        ...     "schema": {
        ...         "type": "object",
        ...         "properties": {
        ...             "info_found": {"type": "string"},
        ...             "summary": {"type": "string"},
        ...         },
        ...         "required": ["info_found", "summary"],
        ...     },
        ... }}
        >>> to_response_format(label_synthesis_schema, "label_synthesis") == expected_lsn
        True
    """
    required = (
        io_schema.required_output
        if io_schema.required_output
        else list(io_schema.output.keys())
    )
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema_name,
            "schema": {
                "type": "object",
                "properties": dict(io_schema.output),
                "required": required,
            },
        },
    }


def to_prompt_output_format_text(io_schema: IOSchema) -> str:
    """Convert the output half of an :class:`IOSchema` into a prompt-embed string.

    The result is a JSON string dump of :attr:`IOSchema.output` (without
    indentation, with non-ASCII characters preserved). It is shaped to
    be embedded verbatim inside the ``output_format`` slot of the prompt
    body so the LLM sees the same contract declared in YAML.

    Args:
        io_schema (IOSchema): The validated I/O schema block.

    Returns:
        str: JSON-dumped text of :attr:`IOSchema.output`.

    Example:
        >>> schema = IOSchema(output={
        ...     "info_found": {"type": "string"},
        ...     "result": {"type": "string"},
        ... })
        >>> to_prompt_output_format_text(schema)
        '{"info_found": {"type": "string"}, "result": {"type": "string"}}'
    """
    return json.dumps(io_schema.output, ensure_ascii=False)
