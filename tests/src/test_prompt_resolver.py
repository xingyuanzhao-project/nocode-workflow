"""Unit tests for :mod:`src.prompt_resolver`.

Every documented branch of :func:`resolve_step_prompt` is exercised
directly. The tests build lightweight stand-ins for
:class:`src.flow_loader.StepConfig` and
:class:`src.node_registry.NodeTypeEntry` so this file has no dependency
on the full flow loader.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import pytest

from src.prompt_resolver import (
    InstructionOverride,
    PromptInline,
    PromptOverride,
    ResolvedPrompt,
    _extract_prompts_ref_key,
    resolve_step_prompt,
)


@dataclass
class _FakeStep:
    """Minimal stand-in for :class:`src.flow_loader.StepConfig`.

    Attributes:
        prompt (Optional[PromptInline]): Inline prompt block.
        prompts_ref (Optional[str]): Reference key into the prompts
            file.
        prompt_overrides (Optional[PromptOverride]): Override directives.
    """

    prompt: Optional[PromptInline] = None
    prompts_ref: Optional[str] = None
    prompt_overrides: Optional[PromptOverride] = None


@dataclass
class _FakeRegistryEntry:
    """Minimal stand-in for :class:`src.node_registry.NodeTypeEntry`.

    Attributes:
        default_prompt_ref (Optional[str]): Default prompt key.
    """

    default_prompt_ref: Optional[str] = None


def _prompts_file() -> Dict[str, Any]:
    """Return a representative prompts file with two keys.

    Returns:
        Dict[str, Any]: Prompts dict with ``summary`` and
        ``label_summary_first`` entries.
    """
    return {
        "summary": {
            "instructions": ["line a", "line b"],
            "output_format": {"summary": "<text>"},
        },
        "label_summary_first": {
            "instructions": ["first line"],
            "output_format": {"summary": "<text>", "info_found": "<TRUE|FALSE>"},
        },
    }


# ---------------------------------------------------------------------
# Precedence: inline > reference > default > None
# ---------------------------------------------------------------------


class TestResolvedPromptPrecedence:
    def test_inline_wins_and_discards_base_output_format(self) -> None:
        step = _FakeStep(prompt=PromptInline(instructions=["only line"]))
        registry_entry = _FakeRegistryEntry(default_prompt_ref="summary")
        resolved = resolve_step_prompt(step, _prompts_file(), registry_entry)
        assert resolved == ResolvedPrompt(
            instructions=["only line"], output_format=None
        )

    def test_reference_only_returns_base_instructions_and_output_format(self) -> None:
        step = _FakeStep(prompts_ref="summary")
        resolved = resolve_step_prompt(
            step, _prompts_file(), _FakeRegistryEntry()
        )
        assert resolved == ResolvedPrompt(
            instructions=["line a", "line b"],
            output_format={"summary": "<text>"},
        )

    def test_registry_default_used_when_step_silent(self) -> None:
        step = _FakeStep()
        registry_entry = _FakeRegistryEntry(default_prompt_ref="label_summary_first")
        resolved = resolve_step_prompt(step, _prompts_file(), registry_entry)
        assert resolved is not None
        assert resolved.instructions == ["first line"]
        assert resolved.output_format == {
            "summary": "<text>",
            "info_found": "<TRUE|FALSE>",
        }

    def test_returns_none_when_no_signal(self) -> None:
        step = _FakeStep()
        resolved = resolve_step_prompt(
            step, _prompts_file(), _FakeRegistryEntry()
        )
        assert resolved is None

    def test_returns_none_when_default_ref_is_missing_from_prompts(self) -> None:
        step = _FakeStep()
        registry_entry = _FakeRegistryEntry(default_prompt_ref="not_there")
        resolved = resolve_step_prompt(step, _prompts_file(), registry_entry)
        # Registry default missing from the file is silently tolerated —
        # processors retain their hardcoded fallback.
        assert resolved is None


# ---------------------------------------------------------------------
# Override directives
# ---------------------------------------------------------------------


class TestOverrideDirectives:
    def test_append_adds_lines_after_base(self) -> None:
        step = _FakeStep(
            prompts_ref="summary",
            prompt_overrides=PromptOverride(
                instructions=InstructionOverride(append=["x", "y"])
            ),
        )
        resolved = resolve_step_prompt(step, _prompts_file(), _FakeRegistryEntry())
        assert resolved is not None
        assert resolved.instructions == ["line a", "line b", "x", "y"]

    def test_prepend_adds_lines_before_base(self) -> None:
        step = _FakeStep(
            prompts_ref="summary",
            prompt_overrides=PromptOverride(
                instructions=InstructionOverride(prepend=["first"])
            ),
        )
        resolved = resolve_step_prompt(step, _prompts_file(), _FakeRegistryEntry())
        assert resolved is not None
        assert resolved.instructions == ["first", "line a", "line b"]

    def test_replace_swaps_base_entirely(self) -> None:
        step = _FakeStep(
            prompts_ref="summary",
            prompt_overrides=PromptOverride(
                instructions=InstructionOverride(replace=["only"])
            ),
        )
        resolved = resolve_step_prompt(step, _prompts_file(), _FakeRegistryEntry())
        assert resolved is not None
        assert resolved.instructions == ["only"]

    def test_replace_then_prepend_then_append_compose_in_order(self) -> None:
        step = _FakeStep(
            prompts_ref="summary",
            prompt_overrides=PromptOverride(
                instructions=InstructionOverride(
                    replace=["base"], prepend=["pre"], append=["post"]
                )
            ),
        )
        resolved = resolve_step_prompt(step, _prompts_file(), _FakeRegistryEntry())
        assert resolved is not None
        assert resolved.instructions == ["pre", "base", "post"]

    def test_overrides_preserve_base_output_format(self) -> None:
        step = _FakeStep(
            prompts_ref="summary",
            prompt_overrides=PromptOverride(
                instructions=InstructionOverride(append=["tail"])
            ),
        )
        resolved = resolve_step_prompt(step, _prompts_file(), _FakeRegistryEntry())
        assert resolved is not None
        assert resolved.output_format == {"summary": "<text>"}


# ---------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------


class TestResolverErrors:
    def test_inline_and_prompts_ref_together_raises(self) -> None:
        step = _FakeStep(
            prompt=PromptInline(instructions=["x"]),
            prompts_ref="summary",
        )
        with pytest.raises(ValueError, match="cannot set both"):
            resolve_step_prompt(step, _prompts_file(), _FakeRegistryEntry())

    def test_overrides_without_prompts_ref_raises(self) -> None:
        step = _FakeStep(
            prompt_overrides=PromptOverride(
                instructions=InstructionOverride(append=["x"])
            )
        )
        with pytest.raises(ValueError, match="requires 'prompts_ref'"):
            resolve_step_prompt(step, _prompts_file(), _FakeRegistryEntry())

    def test_missing_prompts_ref_key_raises_key_error(self) -> None:
        step = _FakeStep(prompts_ref="does_not_exist")
        with pytest.raises(KeyError, match="does_not_exist"):
            resolve_step_prompt(step, _prompts_file(), _FakeRegistryEntry())


# ---------------------------------------------------------------------
# _extract_prompts_ref_key (path-qualified form)
# ---------------------------------------------------------------------


class TestExtractPromptsRefKey:
    def test_bare_key_returned_unchanged(self) -> None:
        assert _extract_prompts_ref_key("summary", None) == "summary"

    def test_path_qualified_key_extracted(self) -> None:
        assert (
            _extract_prompts_ref_key("config/prompts.json::summary", "config/prompts.json")
            == "summary"
        )

    def test_mismatched_path_raises(self) -> None:
        with pytest.raises(ValueError, match="different prompts file"):
            _extract_prompts_ref_key("other.json::summary", "config/prompts.json")

    def test_mismatched_path_allowed_when_flow_path_is_none(self) -> None:
        assert _extract_prompts_ref_key("other.json::summary", None) == "summary"
