"""Accept + reject tests for every validator in :mod:`src.flow_loader`.

Structure mirrors the plan's inventory: one test class per
validator, each covering at least one accept case and every
documented reject case.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest
import yaml
from pydantic import ValidationError

from src.flow_loader import (
    PROVIDER_VALUES,
    UNIT_VALUES,
    VALID_ADJACENT_UNIT_TRANSITIONS,
    DataConfig,
    FlowConfig,
    FlowSchema,
    LLMResource,
    LoggingConfig,
    OutputConfig,
    StepConfig,
    _validate_project_relative_posix_path,
)


_FIXTURES_DIR: Path = Path(__file__).resolve().parent.parent / "fixtures"


def _read_fixture_yaml(name: str) -> Dict[str, Any]:
    """Load ``name`` from ``server/tests/fixtures/`` as a dict.

    Args:
        name (str): Filename relative to the fixtures directory.

    Returns:
        Dict[str, Any]: Parsed YAML content.
    """
    with (_FIXTURES_DIR / name).open("r", encoding="utf-8") as file_handle:
        return yaml.safe_load(file_handle)


def _minimal_valid_flow_body() -> Dict[str, Any]:
    """Return a minimal :class:`FlowConfig`-compatible body.

    The returned body is the smallest shape that passes every
    validator. Tests mutate a deep copy to construct reject cases.

    Returns:
        Dict[str, Any]: Deep-copiable flow body.
    """
    return {
        "schema_version": 1,
        "name": "minimal_valid",
        "description": "",
        "resources": [
            {
                "id": "default",
                "type": "llm_provider",
                "provider": "openrouter",
                "model": "meta-llama/llama-3.1-70b-instruct",
                "api_key_env": "OPENROUTER_API_KEY",
            }
        ],
        "data": {
            "input_csv": "data/df_text_by_report.csv",
        },
        "taxonomy": "config/taxonomy.json",
        "prompts": "config/prompts.json",
        "steps": [
            {"type": "single_summary", "unit": "row"},
        ],
        "output": {"summary_csv": "results/summary.csv"},
    }


# ---------------------------------------------------------------------
# _validate_project_relative_posix_path
# ---------------------------------------------------------------------


class TestProjectRelativePosixPathValidator:
    def test_accepts_plain_relative_path(self) -> None:
        assert _validate_project_relative_posix_path("data/input.csv", "field") == "data/input.csv"

    def test_rejects_empty_string(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            _validate_project_relative_posix_path("   ", "field")

    def test_rejects_backslash(self) -> None:
        with pytest.raises(ValueError, match="backslash"):
            _validate_project_relative_posix_path("data\\input.csv", "field")

    def test_rejects_absolute_posix_path(self) -> None:
        with pytest.raises(ValueError, match="absolute"):
            _validate_project_relative_posix_path("/etc/input.csv", "field")

    def test_rejects_windows_drive_letter(self) -> None:
        with pytest.raises(ValueError, match="Windows drive letter"):
            _validate_project_relative_posix_path("C:/data/input.csv", "field")


# ---------------------------------------------------------------------
# LLMResource
# ---------------------------------------------------------------------


class TestLLMResourceValidators:
    def test_accepts_every_registered_provider(self) -> None:
        for provider in PROVIDER_VALUES:
            resource = LLMResource(id="r", provider=provider, model="m")
            assert resource.provider == provider

    def test_rejects_unknown_provider(self) -> None:
        with pytest.raises(ValidationError) as exc:
            LLMResource(id="r", provider="anthropic", model="m")
        assert "provider must be one of" in str(exc.value)

    def test_rejects_both_api_key_and_api_key_env(self) -> None:
        with pytest.raises(ValidationError) as exc:
            LLMResource(
                id="r",
                provider="openrouter",
                model="m",
                api_key="secret",
                api_key_env="OPENROUTER_API_KEY",
            )
        assert "use exactly one" in str(exc.value)

    def test_accepts_neither_api_key_set(self) -> None:
        # Not an error at load time; the builder resolves at startup.
        resource = LLMResource(id="r", provider="local_vllm", model="m")
        assert resource.api_key is None
        assert resource.api_key_env is None


# ---------------------------------------------------------------------
# DataConfig.validate_input_csv_path
# ---------------------------------------------------------------------


class TestDataConfigInputCsvPath:
    def test_accepts_relative_posix_path(self) -> None:
        config = DataConfig(input_csv="data/df.csv")
        assert config.input_csv == "data/df.csv"

    def test_rejects_absolute_path(self) -> None:
        with pytest.raises(ValidationError, match="absolute"):
            DataConfig(input_csv="/absolute.csv")


# ---------------------------------------------------------------------
# StepConfig
# ---------------------------------------------------------------------


class TestStepConfigValidators:
    def test_accepts_registered_type_and_unit(self) -> None:
        step = StepConfig(type="single_summary", unit="row")
        assert step.type == "single_summary"
        assert step.unit == "row"

    def test_rejects_unknown_step_type(self) -> None:
        with pytest.raises(ValidationError, match="step type must be one of"):
            StepConfig(type="not_a_real_step", unit="row")

    @pytest.mark.parametrize("unit_value", ["row", "document", "entity"])
    def test_accepts_every_registered_unit(self, unit_value: str) -> None:
        step = StepConfig(type="single_summary", unit=unit_value)
        assert step.unit == unit_value

    def test_rejects_unknown_unit(self) -> None:
        with pytest.raises(ValidationError, match="unit must be one of"):
            StepConfig(type="single_summary", unit="batch")

    def test_rejects_both_prompt_and_prompts_ref(self) -> None:
        with pytest.raises(ValidationError, match="Use exactly one"):
            StepConfig(
                type="single_summary",
                unit="row",
                prompt={"instructions": ["x"]},
                prompts_ref="summary",
            )

    def test_rejects_prompt_overrides_without_prompts_ref(self) -> None:
        with pytest.raises(ValidationError, match="Overrides apply on top of a reference"):
            StepConfig(
                type="single_summary",
                unit="row",
                prompt_overrides={"instructions": {"append": ["extra line"]}},
            )

    def test_accepts_prompts_ref_with_overrides(self) -> None:
        step = StepConfig(
            type="single_summary",
            unit="row",
            prompts_ref="summary",
            prompt_overrides={"instructions": {"append": ["extra"]}},
        )
        assert step.prompts_ref == "summary"
        assert step.prompt_overrides is not None


# ---------------------------------------------------------------------
# OutputConfig.validate_csv_paths
# ---------------------------------------------------------------------


class TestOutputConfigCsvPaths:
    def test_accepts_summary_only(self) -> None:
        config = OutputConfig(summary_csv="out/summary.csv")
        assert config.summary_csv == "out/summary.csv"
        assert config.results_csv is None

    def test_rejects_absolute_summary_csv(self) -> None:
        with pytest.raises(ValidationError, match="absolute"):
            OutputConfig(summary_csv="/out/summary.csv")

    @pytest.mark.parametrize(
        "field_name", ["results_csv", "states_csv", "spans_csv"]
    )
    def test_rejects_backslash_in_optional_csv_path(self, field_name: str) -> None:
        with pytest.raises(ValidationError, match="backslash"):
            OutputConfig(summary_csv="out/summary.csv", **{field_name: "out\\x.csv"})

    def test_optional_paths_may_be_none(self) -> None:
        config = OutputConfig(
            summary_csv="out/summary.csv",
            results_csv=None,
            states_csv=None,
            spans_csv=None,
        )
        assert config.model_dump()["results_csv"] is None


# ---------------------------------------------------------------------
# LoggingConfig.validate_log_file_path
# ---------------------------------------------------------------------


class TestLoggingConfigLogFilePath:
    def test_accepts_relative_path_default(self) -> None:
        config = LoggingConfig()
        assert config.file == "processing.log"

    def test_rejects_drive_letter_on_log_file(self) -> None:
        with pytest.raises(ValidationError, match="Windows drive letter"):
            LoggingConfig(file="D:/logs/app.log")


# ---------------------------------------------------------------------
# FlowConfig-level cross-field validators
# ---------------------------------------------------------------------


class TestFlowConfigValidators:
    def test_accepts_minimal_valid_body(self) -> None:
        flow = FlowConfig.model_validate(_minimal_valid_flow_body())
        assert flow.name == "minimal_valid"
        assert len(flow.steps) == 1

    def test_rejects_duplicate_resource_ids(self) -> None:
        body = _minimal_valid_flow_body()
        body["resources"].append(dict(body["resources"][0]))
        with pytest.raises(ValidationError, match="Duplicate LLM resource id"):
            FlowConfig.model_validate(body)

    def test_rejects_unresolved_step_llm_reference(self) -> None:
        body = _minimal_valid_flow_body()
        body["steps"][0]["llm"] = "does_not_exist"
        with pytest.raises(ValidationError, match="not among the declared"):
            FlowConfig.model_validate(body)

    def test_rejects_empty_steps(self) -> None:
        body = _minimal_valid_flow_body()
        body["steps"] = []
        with pytest.raises(ValidationError, match="at least one step"):
            FlowConfig.model_validate(body)

    def test_rejects_bad_adjacent_unit_transition(self) -> None:
        body = _minimal_valid_flow_body()
        body["steps"] = [
            {"type": "single_summary", "unit": "row"},
            {"type": "label_summary", "unit": "entity", "mode": "hybrid"},
        ]
        with pytest.raises(ValidationError, match="is not allowed"):
            FlowConfig.model_validate(body)

    @pytest.mark.parametrize("transition", sorted(VALID_ADJACENT_UNIT_TRANSITIONS))
    def test_allowed_transitions_accepted_by_validator(
        self, transition: tuple[str, str]
    ) -> None:
        from_unit, to_unit = transition
        body = _minimal_valid_flow_body()
        body["steps"] = [
            {"type": _step_type_for_unit(from_unit), "unit": from_unit},
            {"type": _step_type_for_unit(to_unit), "unit": to_unit},
        ]
        # label_summary requires `mode` when unit=entity
        if to_unit == "entity":
            body["steps"][1]["mode"] = "hybrid"
        FlowConfig.model_validate(body)

    def test_every_disallowed_transition_rejected(self) -> None:
        disallowed_pairs = [
            (left_unit, right_unit)
            for left_unit in UNIT_VALUES
            for right_unit in UNIT_VALUES
            if (left_unit, right_unit) not in VALID_ADJACENT_UNIT_TRANSITIONS
        ]
        assert disallowed_pairs  # guard: we expect some disallowed pairs
        for left_unit, right_unit in disallowed_pairs:
            body = _minimal_valid_flow_body()
            body["steps"] = [
                {"type": _step_type_for_unit(left_unit), "unit": left_unit},
                {"type": _step_type_for_unit(right_unit), "unit": right_unit},
            ]
            if right_unit == "entity":
                body["steps"][1]["mode"] = "hybrid"
            with pytest.raises(ValidationError):
                FlowConfig.model_validate(body)

    def test_rejects_absolute_taxonomy_path(self) -> None:
        body = _minimal_valid_flow_body()
        body["taxonomy"] = "/etc/taxonomy.json"
        with pytest.raises(ValidationError, match="absolute"):
            FlowConfig.model_validate(body)

    def test_rejects_absolute_prompts_path(self) -> None:
        body = _minimal_valid_flow_body()
        body["prompts"] = "/etc/prompts.json"
        with pytest.raises(ValidationError, match="absolute"):
            FlowConfig.model_validate(body)


def _step_type_for_unit(unit_value: str) -> str:
    """Return a registered step type whose default unit matches ``unit_value``.

    Needed by the adjacent-unit-transition parametrisation above because
    :meth:`StepConfig.validate_type` rejects unknown names even when the
    step body is later overridden by its ``unit`` field.

    Args:
        unit_value (str): One of ``"row"``, ``"document"``, ``"entity"``.

    Returns:
        str: A real processor step-type id supported by the registry.
    """
    return {
        "row": "single_summary",
        "document": "conversation_summary_first",
        "entity": "label_summary",
    }[unit_value]


# ---------------------------------------------------------------------
# FlowSchema.load_from_path — new graph format tests
# ---------------------------------------------------------------------


class TestFlowSchemaLoadFromPath:
    def test_load_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            FlowSchema.load_from_path(tmp_path / "missing.yml")


# ---------------------------------------------------------------------
# Fixture-driven regression tests (use the shared on-disk fixtures)
# ---------------------------------------------------------------------


class TestFlowFixturesAreRejectedAsExpected:
    @pytest.mark.parametrize(
        "fixture_name",
        [
            "invalid_flow_missing_steps.yml",
            "invalid_flow_bad_unit_transition.yml",
            "invalid_flow_absolute_path.yml",
            "invalid_flow_both_prompt_forms.yml",
        ],
    )
    def test_invalid_fixtures_fail_validation(self, fixture_name: str) -> None:
        body = _read_fixture_yaml(fixture_name)["flow"]
        with pytest.raises(ValidationError):
            FlowConfig.model_validate(body)

    def test_valid_fixture_passes_validation(self) -> None:
        body = _read_fixture_yaml("conversation_summary.yml")["flow"]
        flow = FlowConfig.model_validate(body)
        assert flow.name == "fixture_conversation_summary"
