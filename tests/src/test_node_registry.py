"""Unit tests for :mod:`src.node_registry`.

The registry is a small but load-bearing piece: every flow YAML is
validated against the ids it publishes, and every runtime dispatcher
looks up defaults through it. The tests below exercise every public
helper against happy paths and every documented error branch.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest
import yaml
from pydantic import ValidationError

from src.node_registry import (
    DEFAULT_REGISTRY_PATH,
    NodeTypeEntry,
    NodeTypeRegistry,
    get_default_registry,
    get_entry,
    get_processor_step_types,
    load_registry,
    reset_default_registry_cache,
)


# ---------------------------------------------------------------------
# NodeTypeEntry: cross-field invariants
# ---------------------------------------------------------------------


class TestNodeTypeEntryInvariants:
    def test_llm_backed_entry_requires_llm_provider_resource(self) -> None:
        with pytest.raises(ValidationError, match="llm_provider"):
            NodeTypeEntry(
                id="bad_llm_backed",
                category="processor",
                llm_backed=True,
                requires_resources=[],
            )

    def test_llm_backed_entry_accepts_when_llm_provider_listed(self) -> None:
        entry = NodeTypeEntry(
            id="good_llm_backed",
            category="processor",
            llm_backed=True,
            requires_resources=["llm_provider"],
        )
        assert entry.llm_backed is True

    def test_non_llm_entry_may_omit_requires_resources(self) -> None:
        entry = NodeTypeEntry(
            id="csv_input",
            category="data",
            llm_backed=False,
        )
        assert entry.requires_resources == []


# ---------------------------------------------------------------------
# NodeTypeRegistry: duplicate-id rejection, lookup, category filter
# ---------------------------------------------------------------------


class TestNodeTypeRegistry:
    def test_rejects_duplicate_entry_ids(self) -> None:
        with pytest.raises(ValidationError, match="Duplicate node type entry id"):
            NodeTypeRegistry(
                entries=[
                    NodeTypeEntry(id="dup", category="processor", llm_backed=False),
                    NodeTypeEntry(id="dup", category="processor", llm_backed=False),
                ]
            )

    def test_get_entry_returns_matching_row(self) -> None:
        registry = NodeTypeRegistry(
            entries=[
                NodeTypeEntry(id="csv_input", category="data"),
                NodeTypeEntry(id="single_summary", category="processor", llm_backed=True, requires_resources=["llm_provider"]),
            ]
        )
        entry = registry.get_entry("single_summary")
        assert entry.category == "processor"

    def test_get_entry_raises_key_error_on_unknown_id(self) -> None:
        registry = NodeTypeRegistry(
            entries=[NodeTypeEntry(id="csv_input", category="data")]
        )
        with pytest.raises(KeyError, match="does_not_exist"):
            registry.get_entry("does_not_exist")

    def test_processor_step_types_excludes_data_and_resource_entries(self) -> None:
        registry = NodeTypeRegistry(
            entries=[
                NodeTypeEntry(id="csv_input", category="data"),
                NodeTypeEntry(id="llm_provider", category="resource"),
                NodeTypeEntry(
                    id="single_summary",
                    category="processor",
                    llm_backed=True,
                    requires_resources=["llm_provider"],
                ),
                NodeTypeEntry(
                    id="classification",
                    category="processor",
                    llm_backed=True,
                    requires_resources=["llm_provider"],
                ),
            ]
        )
        assert registry.processor_step_types() == frozenset(
            {"single_summary", "classification"}
        )


# ---------------------------------------------------------------------
# load_registry
# ---------------------------------------------------------------------


class TestLoadRegistry:
    def test_load_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_registry(tmp_path / "does_not_exist.yml")

    def test_load_empty_file_returns_empty_registry(self, tmp_path: Path) -> None:
        empty_yaml = tmp_path / "empty.yml"
        empty_yaml.write_text("", encoding="utf-8")
        registry = load_registry(empty_yaml)
        assert registry.entries == []

    def test_load_rejects_invalid_schema(self, tmp_path: Path) -> None:
        bad_yaml = tmp_path / "bad.yml"
        # llm_backed=True without 'llm_provider' in requires_resources
        bad_yaml.write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "entries": [
                        {
                            "id": "broken",
                            "category": "processor",
                            "llm_backed": True,
                            "requires_resources": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(ValidationError):
            load_registry(bad_yaml)

    def test_load_default_registry_has_expected_processor_ids(self) -> None:
        registry = load_registry(DEFAULT_REGISTRY_PATH)
        processor_ids = registry.processor_step_types()
        # Spot-check: the handful every flow YAML depends on.
        for required_id in [
            "single_summary",
            "conversation_summary_first",
            "conversation_summary_update",
            "label_extraction",
            "label_summary",
            "classification",
        ]:
            assert required_id in processor_ids


# ---------------------------------------------------------------------
# Module-level cached helpers + reset
# ---------------------------------------------------------------------


class TestDefaultRegistryCache:
    def test_get_default_registry_returns_same_instance_twice(self) -> None:
        reset_default_registry_cache()
        first_registry = get_default_registry()
        second_registry = get_default_registry()
        assert first_registry is second_registry

    def test_reset_default_registry_cache_forces_reload(self) -> None:
        reset_default_registry_cache()
        first_registry = get_default_registry()
        reset_default_registry_cache()
        second_registry = get_default_registry()
        assert first_registry is not second_registry

    def test_get_processor_step_types_matches_registry(self) -> None:
        reset_default_registry_cache()
        expected = get_default_registry().processor_step_types()
        assert get_processor_step_types() == expected

    def test_get_entry_uses_default_registry_when_none_passed(self) -> None:
        reset_default_registry_cache()
        entry = get_entry("single_summary")
        assert entry.id == "single_summary"

    def test_get_entry_accepts_custom_registry(self) -> None:
        custom_registry = NodeTypeRegistry(
            entries=[NodeTypeEntry(id="synthetic", category="data")]
        )
        entry = get_entry("synthetic", registry=custom_registry)
        assert entry.category == "data"
