"""Unit tests for the dispatcher-plumbing pieces of :mod:`src.flow_builder`.

Focus on the two pieces the builder owns on its own:

1. :func:`_build_processor_runtime_config` — the function every
   dispatcher calls to resolve step-level overrides. Full rollout
   tests for the dispatchers themselves live behind live LLMs and
   sit in the ``integration`` tier.
2. :class:`_Checkpoint` — the piece that skips already-completed
   entities on resume.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest
import yaml

from src.flow_builder import _Checkpoint, _build_processor_runtime_config
from src.flow_loader import LLMResource, LoggingConfig, ProcessorConfig
from src.io_schema import IOSchema
from src.node_registry import NodeTypeEntry, NodeTypeRegistry
from src.prompt_resolver import (
    InstructionOverride,
    PromptInline,
    PromptOverride,
    ResolvedPrompt,
)


def _default_llm_resource() -> LLMResource:
    """Return a minimal valid :class:`LLMResource`.

    Returns:
        LLMResource: A fresh resource instance for test fixtures.
    """
    return LLMResource(
        id="default",
        provider="openrouter",
        model="meta-llama/llama-3.1-70b-instruct",
        api_key_env="OPENROUTER_API_KEY",
    )


def _prompts_payload() -> Dict[str, Any]:
    """Return a representative prompts JSON payload.

    Returns:
        Dict[str, Any]: Dict with ``summary`` and ``label_summary_first``
        keys carrying instruction lists and output formats.
    """
    return {
        "summary": {
            "instructions": ["base instruction"],
            "output_format": {"summary": "<text>"},
        },
        "label_summary_first": {
            "instructions": ["first line"],
            "output_format": {
                "summary": "<text>",
                "info_found": "<TRUE|FALSE>",
            },
        },
    }


def _logging_config() -> LoggingConfig:
    """Return a default :class:`LoggingConfig`.

    Returns:
        LoggingConfig: Default logging config for tests.
    """
    return LoggingConfig()


def _minimal_registry() -> NodeTypeRegistry:
    """Return a tiny registry covering the fixtures this file needs.

    Returns:
        NodeTypeRegistry: Registry with ``single_summary`` and
        ``label_summary`` entries populated with realistic defaults.
    """
    return NodeTypeRegistry(
        entries=[
            NodeTypeEntry(
                id="single_summary",
                category="processor",
                llm_backed=True,
                requires_resources=["llm_provider"],
                default_prompt_ref="summary",
                default_io_schema={
                    "input": {"input_text": {"type": "string"}},
                    "output": {
                        "info_found": {"type": "string"},
                        "summary": {"type": "string"},
                    },
                },
            ),
            NodeTypeEntry(
                id="label_summary",
                category="processor",
                llm_backed=True,
                requires_resources=["llm_provider"],
                default_prompt_ref="label_summary_first",
                default_io_schema={
                    "input": {"input_text": {"type": "string"}},
                    "output": {"summary": {"type": "string"}},
                },
            ),
        ]
    )


# ---------------------------------------------------------------------
# _build_processor_runtime_config
# ---------------------------------------------------------------------


class TestBaseRuntimeConfig:
    def test_base_mode_emits_four_keys_only(self) -> None:
        config = _build_processor_runtime_config(
            resource=_default_llm_resource(),
            prompts_payload=_prompts_payload(),
            logging_config=_logging_config(),
        )
        assert set(config.keys()) == {"model", "processing", "prompts", "logging"}
        assert config["model"]["name"] == "meta-llama/llama-3.1-70b-instruct"
        assert config["processing"]["temperature"] == 0.0

    def test_base_mode_ignores_step_and_registry(self) -> None:
        # When step is omitted, no override keys appear.
        config = _build_processor_runtime_config(
            resource=_default_llm_resource(),
            prompts_payload=_prompts_payload(),
            logging_config=_logging_config(),
        )
        assert "io_schema_resolved" not in config
        assert "prompt_resolved" not in config


class TestStepLevelResolution:
    def test_registry_defaults_applied_when_step_has_no_overrides(self) -> None:
        step = ProcessorConfig.model_construct(type="single_summary", unit="row")
        config = _build_processor_runtime_config(
            resource=_default_llm_resource(),
            prompts_payload=_prompts_payload(),
            logging_config=_logging_config(),
            step=step,
            registry=_minimal_registry(),
        )
        resolved_io_schema: IOSchema = config["io_schema_resolved"]
        assert resolved_io_schema.output == {
            "info_found": {"type": "string"},
            "summary": {"type": "string"},
        }
        resolved_prompt: ResolvedPrompt = config["prompt_resolved"]
        assert resolved_prompt.instructions == ["base instruction"]

    def test_step_io_schema_override_wins_over_registry_default(self) -> None:
        override = IOSchema(output={"custom": {"type": "string"}})
        step = ProcessorConfig.model_construct(type="single_summary", unit="row", io_schema=override)
        config = _build_processor_runtime_config(
            resource=_default_llm_resource(),
            prompts_payload=_prompts_payload(),
            logging_config=_logging_config(),
            step=step,
            registry=_minimal_registry(),
        )
        assert config["io_schema_resolved"].output == {"custom": {"type": "string"}}

    def test_step_prompt_overrides_append_to_registry_default(self) -> None:
        step = ProcessorConfig.model_construct(
            type="single_summary",
            unit="row",
            prompts_ref="summary",
            prompt_overrides=PromptOverride(
                instructions=InstructionOverride(append=["extra"])
            ),
        )
        config = _build_processor_runtime_config(
            resource=_default_llm_resource(),
            prompts_payload=_prompts_payload(),
            logging_config=_logging_config(),
            step=step,
            registry=_minimal_registry(),
        )
        resolved_prompt: ResolvedPrompt = config["prompt_resolved"]
        assert resolved_prompt.instructions == ["base instruction", "extra"]

    def test_inline_prompt_replaces_registry_default(self) -> None:
        step = ProcessorConfig.model_construct(
            type="single_summary",
            unit="row",
            prompt=PromptInline(instructions=["inline only"]),
            prompts_ref=None,
            prompt_overrides=None,
            io_schema=None,
        )
        config = _build_processor_runtime_config(
            resource=_default_llm_resource(),
            prompts_payload=_prompts_payload(),
            logging_config=_logging_config(),
            step=step,
            registry=_minimal_registry(),
        )
        resolved_prompt: ResolvedPrompt = config["prompt_resolved"]
        assert resolved_prompt.instructions == ["inline only"]
        assert resolved_prompt.output_format is None

    def test_step_without_registry_raises(self) -> None:
        step = ProcessorConfig.model_construct(type="single_summary", unit="row")
        with pytest.raises(ValueError, match="requires 'registry'"):
            _build_processor_runtime_config(
                resource=_default_llm_resource(),
                prompts_payload=_prompts_payload(),
                logging_config=_logging_config(),
                step=step,
            )

    def test_unknown_processor_type_raises_key_error(self) -> None:
        step = ProcessorConfig.model_construct(type="not_registered", unit="row")
        with pytest.raises(KeyError):
            _build_processor_runtime_config(
                resource=_default_llm_resource(),
                prompts_payload=_prompts_payload(),
                logging_config=_logging_config(),
                step=step,
                registry=_minimal_registry(),
            )


# ---------------------------------------------------------------------
# _Checkpoint
# ---------------------------------------------------------------------


class TestCheckpointRoundTrip:
    def test_empty_when_no_file(self, tmp_path: Path) -> None:
        checkpoint = _Checkpoint(tmp_path, flow_name="x")
        assert checkpoint.completed_entity_ids() == set()

    def test_mark_completed_persists_across_instances(self, tmp_path: Path) -> None:
        checkpoint = _Checkpoint(tmp_path, flow_name="x")
        checkpoint.mark_completed("entity_a")
        checkpoint.mark_completed(42)
        # New instance reads the same file.
        reloaded = _Checkpoint(tmp_path, flow_name="x")
        assert reloaded.completed_entity_ids() == {"entity_a", "42"}

    def test_mark_completed_keeps_json_sorted(self, tmp_path: Path) -> None:
        checkpoint = _Checkpoint(tmp_path, flow_name="x")
        checkpoint.mark_completed("zz")
        checkpoint.mark_completed("aa")
        with checkpoint.completed_file.open("r", encoding="utf-8") as file_handle:
            document = json.load(file_handle)
        assert document == {"completed": ["aa", "zz"]}

    def test_clear_removes_file(self, tmp_path: Path) -> None:
        checkpoint = _Checkpoint(tmp_path, flow_name="x")
        checkpoint.mark_completed("entity_a")
        assert checkpoint.completed_file.exists()
        checkpoint.clear()
        assert not checkpoint.completed_file.exists()
        assert checkpoint.completed_entity_ids() == set()

    def test_resume_filter_semantics(self, tmp_path: Path) -> None:
        """Assert the ``completed`` set is the right shape for filtering.

        The dispatcher does ``entity for entity in entities if entity
        not in completed_ids`` so the test mirrors that predicate to
        keep the test body close to the caller's behaviour.
        """
        checkpoint = _Checkpoint(tmp_path, flow_name="x")
        for entity_id in ("alpha", "bravo"):
            checkpoint.mark_completed(entity_id)
        completed_set = checkpoint.completed_entity_ids()
        all_entity_ids: List[str] = ["alpha", "bravo", "charlie", "delta"]
        pending_ids = [eid for eid in all_entity_ids if eid not in completed_set]
        assert pending_ids == ["charlie", "delta"]
