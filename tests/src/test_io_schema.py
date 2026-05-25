"""Unit tests for :mod:`src.io_schema`.

The module's docstring already carries five byte-for-byte doctest
round-trips against the hardcoded response formats in
:mod:`src.processors`; those are executed here via ``--doctest-modules``
on demand. The tests below add two things the doctests do not cover:

1. Every ``default_io_schema`` in ``workflows/node_types.yaml`` round-trips
   through :func:`to_response_format` and :func:`to_prompt_output_format_text`
   without raising. This catches registry entries that silently drift
   away from the shape :class:`IOSchema` expects.
2. The generated JSON Schema shape is a JSON Schema subset (``type``,
   ``properties``, ``required``) so downstream providers that parse it
   into their own validators do not choke.
"""

from __future__ import annotations

import json

import pytest

from src.io_schema import IOSchema, to_prompt_output_format_text, to_response_format
from src.node_registry import get_default_registry


def _iter_default_io_schemas():
    """Yield ``(entry_id, default_io_schema_dict)`` for every entry that declares one.

    Yields:
        Tuple[str, Dict[str, Any]]: Registry id and default dict.
    """
    registry = get_default_registry()
    for entry in registry.entries:
        if entry.default_io_schema is None:
            continue
        yield entry.id, entry.default_io_schema


@pytest.mark.parametrize(
    "entry_id, default_io_schema",
    list(_iter_default_io_schemas()),
    ids=lambda value: value if isinstance(value, str) else "schema",
)
class TestDefaultIOSchemas:
    def test_constructs_io_schema_instance(
        self, entry_id: str, default_io_schema: dict
    ) -> None:
        schema = IOSchema(**default_io_schema)
        assert "output" in schema.model_dump()

    def test_to_response_format_preserves_field_order(
        self, entry_id: str, default_io_schema: dict
    ) -> None:
        schema = IOSchema(**default_io_schema)
        response_format = to_response_format(schema, schema_name=entry_id)
        json_schema = response_format["json_schema"]["schema"]
        assert json_schema["type"] == "object"
        assert json_schema["required"] == list(schema.output.keys())
        assert list(json_schema["properties"].keys()) == list(schema.output.keys())

    def test_to_prompt_output_format_text_is_json_serialisable(
        self, entry_id: str, default_io_schema: dict
    ) -> None:
        schema = IOSchema(**default_io_schema)
        text = to_prompt_output_format_text(schema)
        # Round-trip through json to make sure every value was JSON-safe.
        assert json.loads(text) == dict(schema.output)


class TestIOSchemaEmpty:
    def test_empty_output_produces_empty_required_list(self) -> None:
        schema = IOSchema(output={})
        response_format = to_response_format(schema, schema_name="empty")
        assert response_format["json_schema"]["schema"]["required"] == []
        assert response_format["json_schema"]["schema"]["properties"] == {}

    def test_empty_output_text_is_empty_json_object(self) -> None:
        assert to_prompt_output_format_text(IOSchema(output={})) == "{}"

    def test_input_block_does_not_flow_into_response_format(self) -> None:
        schema = IOSchema(
            input={"some_input_field": {"data_type": "string"}},
            output={"summary": {"data_type": "string"}},
        )
        response_format = to_response_format(schema, schema_name="with_input")
        assert "some_input_field" not in response_format["json_schema"]["schema"]["properties"]
        assert "input" not in response_format["json_schema"]["schema"]


class TestIOSchemaExtraFieldsRejected:
    def test_extra_top_level_field_raises(self) -> None:
        with pytest.raises(ValueError):
            IOSchema(
                input={},
                output={"summary": {"data_type": "string"}},
                unexpected_field="nope",  # type: ignore[call-arg]
            )
