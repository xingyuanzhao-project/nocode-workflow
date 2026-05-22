"""Unit tests for :class:`server.services.flow_validation.FlowValidator`.

The validator wraps :class:`src.flow_loader.FlowSchema`. Its job is to
convert a raw flow dict into a :class:`FlowValidationResponse` with a
flattened error list. Tests here cover accept, reject, and flattening.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from server.schemas.flow import FlowValidationResponse
from server.services.flow_validation import FlowValidator


def _read_fixture_flow(fixtures_dir: Path, filename: str) -> dict:
    """Parse a fixture YAML and return its ``flow`` block.

    Args:
        fixtures_dir (Path): The fixtures directory.
        filename (str): YAML file name under ``fixtures_dir``.

    Returns:
        dict: The ``flow`` block.
    """
    with (fixtures_dir / filename).open("r", encoding="utf-8") as file_handle:
        return yaml.safe_load(file_handle)["flow"]


class TestFlowValidator:
    def test_valid_flow_fixture_passes(
        self, flow_validator: FlowValidator, valid_flow_body: dict
    ) -> None:
        response = flow_validator.validate(valid_flow_body)
        assert response.valid is True
        assert response.errors == []

    @pytest.mark.parametrize(
        "fixture_name",
        [
            "invalid_flow_missing_steps.yml",
            "invalid_flow_bad_unit_transition.yml",
            "invalid_flow_absolute_path.yml",
            "invalid_flow_both_prompt_forms.yml",
        ],
    )
    def test_invalid_fixtures_produce_errors(
        self,
        flow_validator: FlowValidator,
        fixtures_dir: Path,
        fixture_name: str,
    ) -> None:
        response = flow_validator.validate(
            _read_fixture_flow(fixtures_dir, fixture_name)
        )
        assert response.valid is False
        assert response.errors, "Invalid fixture should produce at least one error."

    def test_errors_preserve_loc_path(
        self, flow_validator: FlowValidator, fixtures_dir: Path
    ) -> None:
        response = flow_validator.validate(
            _read_fixture_flow(fixtures_dir, "invalid_flow_absolute_path.yml")
        )
        # The offending field is ``data.input_csv``; the loc path should
        # include the containing key so clients can render the error at
        # the right field.
        locations = [issue.loc for issue in response.errors]
        assert any("input_csv" in segment for loc in locations for segment in loc)

    def test_errors_are_typed(
        self, flow_validator: FlowValidator, fixtures_dir: Path
    ) -> None:
        response = flow_validator.validate(
            _read_fixture_flow(fixtures_dir, "invalid_flow_missing_steps.yml")
        )
        for issue in response.errors:
            assert isinstance(issue.msg, str) and issue.msg
            assert isinstance(issue.type, str) and issue.type

    def test_response_shape_is_pydantic(
        self, flow_validator: FlowValidator, valid_flow_body: dict
    ) -> None:
        response = flow_validator.validate(valid_flow_body)
        assert isinstance(response, FlowValidationResponse)
