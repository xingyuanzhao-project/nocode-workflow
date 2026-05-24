"""Ad-hoc sanity checks for the updated flow_loader module.

Run with ``.venv/Scripts/python.exe _verify_flow_loader.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pydantic import ValidationError

from src.flow_loader import (
    UNIT_VALUES,
    VALID_ADJACENT_UNIT_TRANSITIONS,
    FlowConfig,
    ProcessorConfig,
    _registered_processor_types,
)


def _base_flow_dict(processor_dicts):
    """Build a minimal valid FlowConfig dict with the given processors."""
    return {
        "schema_version": 1,
        "name": "dummy",
        "description": "",
        "resources": [
            {
                "id": "default",
                "provider": "openrouter",
                "model": "meta-llama/llama-3.1-8b-instruct",
            }
        ],
        "data": {
            "input_csv": "df_text_by_report.csv",
        },
        "taxonomy": "config/taxonomy.json",
        "prompts": "config/prompts.json",
        "processors": processor_dicts,
        "output": {"summary_csv": "out.csv"},
    }


def test_processor_type_validation():
    """Confirm only registered processor types pass ProcessorConfig validation."""
    registered = _registered_processor_types()
    expected_registered = {"processor"}
    assert registered == expected_registered, (
        f"Expected {expected_registered}, got {registered}"
    )
    assert "evaluation" not in registered
    try:
        ProcessorConfig(type="evaluation", unit="row")
    except ValidationError as error:
        assert "processor type must be one of" in str(error)
    else:
        raise AssertionError("Expected validation error for type='evaluation'")

    ProcessorConfig(type="processor", unit="row")
    print("test_processor_type_validation OK")


def test_prompt_mutual_exclusion():
    """Confirm ProcessorConfig rejects combining inline prompt with prompts_ref."""
    try:
        ProcessorConfig(
            type="processor",
            unit="row",
            prompt={"instructions": ["a"]},
            prompts_ref="summary",
        )
    except ValidationError as error:
        assert "both inline 'prompt' and 'prompts_ref'" in str(error)
    else:
        raise AssertionError("Expected prompt/prompts_ref exclusion error")

    try:
        ProcessorConfig(
            type="processor",
            unit="row",
            prompt_overrides={"instructions": {"append": ["x"]}},
        )
    except ValidationError as error:
        assert "'prompt_overrides' without 'prompts_ref'" in str(error)
    else:
        raise AssertionError("Expected prompt_overrides-without-ref error")

    ProcessorConfig(
        type="processor",
        unit="row",
        prompts_ref="summary",
        prompt_overrides={"instructions": {"append": ["x"]}},
    )
    ProcessorConfig(
        type="processor",
        unit="row",
        prompt={"instructions": ["a"]},
    )
    ProcessorConfig(type="processor", unit="row", prompts_ref="summary")
    print("test_prompt_mutual_exclusion OK")


def test_adjacent_unit_transitions_valid_pairs():
    """Confirm FlowConfig accepts legal adjacent processor unit pairs."""
    assert VALID_ADJACENT_UNIT_TRANSITIONS == frozenset({("row", "row")})
    assert UNIT_VALUES == frozenset({"row"})

    ok_flow = FlowConfig.model_validate(
        _base_flow_dict(
            [
                {"type": "processor", "unit": "row"},
                {"type": "processor", "unit": "row"},
            ]
        )
    )
    assert len(ok_flow.processors) == 2
    print("test_adjacent_unit_transitions_valid_pairs OK")


def test_adjacent_unit_transitions_invalid_pairs():
    """No invalid pairs when only unit=row exists — placeholder test."""
    print("test_adjacent_unit_transitions_invalid_pairs OK (no multi-unit support)")


if __name__ == "__main__":
    test_processor_type_validation()
    test_prompt_mutual_exclusion()
    test_adjacent_unit_transitions_valid_pairs()
    test_adjacent_unit_transitions_invalid_pairs()
    print("all flow_loader sanity checks passed")
