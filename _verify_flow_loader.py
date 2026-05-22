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
    StepConfig,
    _registered_processor_step_types,
)


def _base_flow_dict(step_dicts):
    """Build a minimal valid FlowConfig dict with the given steps.

    Args:
        step_dicts: List of step configuration dicts to embed under the
            ``steps`` key.

    Returns:
        Complete flow configuration dict with dummy resource, data,
        taxonomy, prompts, and output settings.
    """
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
            "column_roles": {
                "text": "text",
                "entity_id": "victim",
                "doc_id": "report_id",
                "sort_by": "date",
            },
        },
        "taxonomy": "config/taxonomy.json",
        "prompts": "config/prompts.json",
        "steps": step_dicts,
        "output": {"summary_csv": "out.csv"},
    }


def test_step_type_validation():
    """Confirm only registered processor types pass StepConfig validation."""
    registered = _registered_processor_step_types()
    expected_registered = {
        "classification",
        "conversation_summary_first",
        "conversation_summary_update",
        "label_extraction",
        "label_summary",
        "single_summary",
    }
    assert registered == expected_registered, (
        f"Expected {expected_registered}, got {registered}"
    )
    assert "evaluation" not in registered
    try:
        StepConfig(type="evaluation", unit="row")
    except ValidationError as error:
        assert "step type must be one of" in str(error)
    else:
        raise AssertionError("Expected validation error for type='evaluation'")

    StepConfig(type="single_summary", unit="row")
    print("test_step_type_validation OK")


def test_prompt_mutual_exclusion():
    """Confirm StepConfig rejects combining inline prompt with prompts_ref."""
    try:
        StepConfig(
            type="single_summary",
            unit="row",
            prompt={"instructions": ["a"]},
            prompts_ref="summary",
        )
    except ValidationError as error:
        assert "both inline 'prompt' and 'prompts_ref'" in str(error)
    else:
        raise AssertionError("Expected prompt/prompts_ref exclusion error")

    try:
        StepConfig(
            type="single_summary",
            unit="row",
            prompt_overrides={"instructions": {"append": ["x"]}},
        )
    except ValidationError as error:
        assert "'prompt_overrides' without 'prompts_ref'" in str(error)
    else:
        raise AssertionError("Expected prompt_overrides-without-ref error")

    StepConfig(
        type="single_summary",
        unit="row",
        prompts_ref="summary",
        prompt_overrides={"instructions": {"append": ["x"]}},
    )
    StepConfig(
        type="single_summary",
        unit="row",
        prompt={"instructions": ["a"]},
    )
    StepConfig(type="single_summary", unit="row", prompts_ref="summary")
    print("test_prompt_mutual_exclusion OK")


def test_adjacent_unit_transitions_valid_pairs():
    """Confirm FlowConfig accepts legal adjacent-step unit pairs."""
    assert VALID_ADJACENT_UNIT_TRANSITIONS == frozenset(
        {
            ("row", "row"),
            ("document", "document"),
            ("document", "entity"),
            ("entity", "entity"),
        }
    )
    assert UNIT_VALUES == frozenset({"row", "document", "entity"})

    ok_flow = FlowConfig.model_validate(
        _base_flow_dict(
            [
                {"type": "single_summary", "unit": "document"},
                {"type": "single_summary", "unit": "entity", "group_by": "entity"},
            ]
        )
    )
    assert len(ok_flow.steps) == 2

    ok_rowrow = FlowConfig.model_validate(
        _base_flow_dict(
            [
                {"type": "single_summary", "unit": "row"},
                {"type": "classification", "unit": "row"},
            ]
        )
    )
    assert len(ok_rowrow.steps) == 2
    print("test_adjacent_unit_transitions_valid_pairs OK")


def test_adjacent_unit_transitions_invalid_pairs():
    """Confirm FlowConfig rejects every illegal adjacent-step unit pair."""
    invalid_cases = [
        ("document", "row"),
        ("row", "document"),
        ("row", "entity"),
        ("entity", "document"),
        ("entity", "row"),
    ]
    for prev_unit, curr_unit in invalid_cases:
        try:
            FlowConfig.model_validate(
                _base_flow_dict(
                    [
                        {"type": "single_summary", "unit": prev_unit},
                        {"type": "single_summary", "unit": curr_unit},
                    ]
                )
            )
        except ValidationError as error:
            message = str(error)
            assert "Invalid adjacent unit transition" in message, message
            assert f"{prev_unit!r}\u2192{curr_unit!r}" in message, message
        else:
            raise AssertionError(
                f"Expected ValidationError for {prev_unit}->{curr_unit}"
            )
    print("test_adjacent_unit_transitions_invalid_pairs OK")


if __name__ == "__main__":
    test_step_type_validation()
    test_prompt_mutual_exclusion()
    test_adjacent_unit_transitions_valid_pairs()
    test_adjacent_unit_transitions_invalid_pairs()
    print("all flow_loader sanity checks passed")
