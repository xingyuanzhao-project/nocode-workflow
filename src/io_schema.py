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
:class:`src.flow_loader.ProcessorConfig` typed as ``Optional[IOSchema]`` so
users can override the schema per processor. :mod:`src.flow_builder` resolves
the effective ``io_schema`` (processor override → registry default →
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
        Derive JSON Schema type from ``data_type``:

        >>> schema = IOSchema(output={
        ...     "entity": {"data_type": "string"},
        ...     "strength": {"data_type": "numeric"},
        ...     "label": {"data_type": "category", "options": ["A", "B"]},
        ... })
        >>> result = to_response_format(schema, "extraction")
        >>> result == {"type": "json_schema", "json_schema": {
        ...     "name": "extraction",
        ...     "schema": {
        ...         "type": "object",
        ...         "properties": {
        ...             "entity": {"type": "string"},
        ...             "strength": {"type": "number"},
        ...             "label": {"type": "string"},
        ...         },
        ...         "required": ["entity", "strength", "label"],
        ...     },
        ... }}
        True

        Binary and category both map to JSON Schema ``"string"``:

        >>> schema = IOSchema(output={
        ...     "is_relevant": {"data_type": "binary"},
        ...     "category": {"data_type": "category"},
        ... })
        >>> props = to_response_format(schema, "test")["json_schema"]["schema"]["properties"]
        >>> props["is_relevant"]
        {'type': 'string'}
        >>> props["category"]
        {'type': 'string'}

        Integer maps to JSON Schema ``"integer"``:

        >>> schema = IOSchema(output={"count": {"data_type": "integer"}})
        >>> to_response_format(schema, "test")["json_schema"]["schema"]["properties"]["count"]
        {'type': 'integer'}
    """
    _DATA_TYPE_TO_JSON_TYPE = {
        "string": "string",
        "binary": "string",
        "category": "string",
        "numeric": "number",
        "integer": "integer",
    }

    clean_properties: Dict[str, Any] = {}
    for field_name, field_spec in io_schema.output.items():
        if isinstance(field_spec, dict):
            data_type = field_spec.get("data_type", "string")
            clean_properties[field_name] = {
                "type": _DATA_TYPE_TO_JSON_TYPE.get(data_type, "string"),
            }
        else:
            clean_properties[field_name] = field_spec

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
                "properties": clean_properties,
                "required": required,
            },
        },
    }


def to_prompt_output_format_text(io_schema: IOSchema) -> str:
    """Convert the output half of an :class:`IOSchema` into a prompt-embed string.

    Produces a structured description for each output field that includes
    the JSON Schema type plus any constraints (valid options for category
    fields, range/interval for numeric fields). This gives the LLM
    explicit guidance on what values are acceptable.

    Args:
        io_schema (IOSchema): The validated I/O schema block.

    Returns:
        str: JSON-dumped text describing each output field.
    """
    descriptors: Dict[str, Any] = {}
    for field_name, field_spec in io_schema.output.items():
        if not isinstance(field_spec, dict):
            descriptors[field_name] = field_spec
            continue

        data_type = field_spec.get("data_type", "string")
        entry: Dict[str, Any] = {"data_type": data_type}

        options = field_spec.get("options")
        if isinstance(options, list) and options:
            entry["valid_options"] = options

        range_start = field_spec.get("range_start")
        range_end = field_spec.get("range_end")
        if range_start or range_end:
            entry["range"] = f"{range_start or ''} to {range_end or ''}"

        step_val = field_spec.get("step")
        if step_val:
            entry["step"] = step_val

        descriptors[field_name] = entry

    return json.dumps(descriptors, ensure_ascii=False)
