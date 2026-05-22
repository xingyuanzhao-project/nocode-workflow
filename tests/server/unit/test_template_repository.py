"""Unit tests for :class:`server.services.template_repository.TemplateRepository`.

Covers valid templates loading, broken templates being silently
excluded from :meth:`list`, and :meth:`get` raising for unknown or
broken ids.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from server.services.flow_validation import FlowValidator
from server.services.template_repository import TemplateRepository


@pytest.fixture
def template_fixture_dir(tmp_path: Path, valid_flow_body: dict) -> Path:
    """Build a temporary templates directory with one valid + one broken YAML.

    Returns:
        Path: Directory containing ``valid.yml`` and ``broken.yml``.
    """
    import yaml

    valid_yaml = tmp_path / "valid.yml"
    valid_yaml.write_text(
        yaml.safe_dump({"flow": valid_flow_body}, sort_keys=False), encoding="utf-8"
    )
    broken_yaml = tmp_path / "broken.yml"
    broken_yaml.write_text(
        yaml.safe_dump({"flow": {"name": "broken", "steps": []}}, sort_keys=False),
        encoding="utf-8",
    )
    return tmp_path


class TestTemplateRepository:
    def test_list_excludes_broken_templates(
        self, template_fixture_dir: Path, flow_validator: FlowValidator
    ) -> None:
        repository = TemplateRepository(
            templates_dir=template_fixture_dir, validator=flow_validator
        )
        listed_items = repository.list()
        assert {item.id for item in listed_items} == {"valid"}

    def test_get_valid_template_returns_body(
        self, template_fixture_dir: Path, flow_validator: FlowValidator
    ) -> None:
        repository = TemplateRepository(
            templates_dir=template_fixture_dir, validator=flow_validator
        )
        detail = repository.get("valid")
        assert detail.id == "valid"
        assert "steps" in detail.flow

    def test_get_unknown_template_raises(
        self, template_fixture_dir: Path, flow_validator: FlowValidator
    ) -> None:
        repository = TemplateRepository(
            templates_dir=template_fixture_dir, validator=flow_validator
        )
        with pytest.raises(FileNotFoundError):
            repository.get("does_not_exist")

    def test_get_broken_template_raises(
        self, template_fixture_dir: Path, flow_validator: FlowValidator
    ) -> None:
        repository = TemplateRepository(
            templates_dir=template_fixture_dir, validator=flow_validator
        )
        with pytest.raises(FileNotFoundError, match="failed validation"):
            repository.get("broken")


class TestDefaultTemplates:
    def test_every_shipped_template_loads(self, flow_validator: FlowValidator) -> None:
        from server.services.template_repository import DEFAULT_TEMPLATES_DIR

        repository = TemplateRepository(
            templates_dir=DEFAULT_TEMPLATES_DIR, validator=flow_validator
        )
        shipped_ids = {item.id for item in repository.list()}
        assert {
            "label_extraction_summary",
            "flat_summary_classification",
            "full_pipeline",
        } <= shipped_ids
