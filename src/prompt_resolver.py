"""Resolution of the effective prompt dict for one processor step.

A flow YAML step can supply its prompt in four mutually non-exclusive
ways documented in ``docs/gui_plan.md`` section 1.8:

1. Inline ``prompt`` block with an ``instructions`` list that replaces
   every default.
2. ``prompts_ref`` pointing at a key in the flow-level ``prompts.json``.
3. ``prompts_ref`` plus ``prompt_overrides`` whose ``append`` / ``prepend``
   / ``replace`` directives mutate the referenced instruction list.
4. Nothing — the resolver falls back to the registry entry's
   ``default_prompt_ref`` and, if that is also absent, returns ``None``
   so each processor's historical hardcoded behavior still applies.

Contents and relationships
--------------------------

- :class:`InstructionOverride` — the three mutation directives
  (``append``, ``prepend``, ``replace``) that apply to the base
  instruction list.
- :class:`PromptOverride` — wraps an :class:`InstructionOverride` under
  the ``instructions`` key, matching the YAML shape shown in
  ``docs/gui_plan.md``.
- :class:`PromptInline` — the inline prompt block carrying a required
  ``instructions`` list that fully replaces any referenced base.
- :class:`ResolvedPrompt` — the dataclass-like model the builder injects
  into :mod:`src.processors`' runtime config under the key
  ``prompt_resolved``.
- :func:`resolve_step_prompt` — the single entry point. Takes the
  :class:`src.flow_loader.ProcessorConfig`, the already-loaded
  ``config/prompts.json`` payload, and the processor's registry entry;
  returns a :class:`ResolvedPrompt` or ``None``.

How the rest of the system uses this module
-------------------------------------------

:mod:`src.flow_builder` imports the Pydantic models so they are
addressable from :class:`src.flow_loader.ProcessorConfig` field types,
and imports :func:`resolve_step_prompt` to compute the per-processor
resolved prompt before each processor is instantiated.

Invariants enforced by this module
----------------------------------

- Inline :attr:`PromptInline` and ``prompts_ref`` are mutually
  exclusive. :meth:`resolve_step_prompt` raises :class:`ValueError` if
  both are set.
- ``prompt_overrides`` requires ``prompts_ref`` to be set. Applying a
  delta on top of an inline prompt is rejected.
- When a ``prompts_ref`` of the form ``"path/to/file.json::key"`` is
  supplied and the path matches the flow-level prompts file, the key
  suffix is looked up in that file. Paths pointing at a different file
  are rejected because the runner wires exactly one prompts file per
  flow.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class InstructionOverride(BaseModel):
    """Mutation directives applied to a base instruction list.

    Attributes:
        append (Optional[List[str]]): Strings appended after the base
            instructions. Applied last in the override pipeline.
        prepend (Optional[List[str]]): Strings inserted before the base
            instructions. Applied after ``replace`` but before
            ``append``.
        replace (Optional[List[str]]): Replacement list. When set, the
            base instruction list is discarded and replaced with
            exactly these strings before ``prepend`` and ``append``
            apply.
    """

    model_config = ConfigDict(extra="forbid")

    append: Optional[List[str]] = None
    prepend: Optional[List[str]] = None
    replace: Optional[List[str]] = None


class PromptOverride(BaseModel):
    """Delta applied on top of a ``prompts_ref`` base.

    Attributes:
        instructions (Optional[InstructionOverride]): Mutations applied
            to the base instruction list. ``None`` means no mutation
            (the base list is used as-is).
    """

    model_config = ConfigDict(extra="forbid")

    instructions: Optional[InstructionOverride] = None


class PromptInline(BaseModel):
    """Inline prompt block declared directly on a step.

    Fully replaces any referenced base when set. Used by users who want
    to write the entire prompt in YAML instead of pointing at
    ``prompts.json``.

    Attributes:
        instructions (List[str]): Final instruction list sent to the
            LLM for this step.
        output_format (Optional[Any]): Optional ``output_format`` dict
            that the GUI may include alongside the inline instructions.
            Carried through to :class:`ResolvedPrompt` when present.
    """

    model_config = ConfigDict(extra="forbid")

    instructions: List[str] = Field(default_factory=list)
    output_format: Optional[Any] = None


class ResolvedPrompt(BaseModel):
    """Effective prompt after the four-level resolution.

    The builder injects this object (or ``None``) into the per-step
    runtime config under the key ``prompt_resolved``. Each
    ``_get_*_args`` method in :mod:`src.processors` reads that key and
    uses these fields to build the prompt body.

    Attributes:
        instructions (List[str]): Final instruction list shown to the
            LLM.
        output_format (Optional[Any]): Optional ``output_format`` dict
            carried from the referenced ``prompts.json`` entry. ``None``
            means the processor should derive an output format from the
            step's ``io_schema`` (when present) or fall back to its
            hardcoded behavior.
    """

    model_config = ConfigDict(extra="forbid")

    instructions: List[str] = Field(default_factory=list)
    output_format: Optional[Any] = None


def _extract_prompts_ref_key(prompts_ref: str, flow_prompts_path: Optional[str]) -> str:
    """Extract the lookup key from a ``prompts_ref`` string.

    Accepts both the bare-key form (``"summary"``) and the
    path-qualified form (``"config/prompts.json::summary"``). When the
    path-qualified form is used and ``flow_prompts_path`` is supplied,
    the path component must match the flow-level prompts file.

    Args:
        prompts_ref (str): The raw ``prompts_ref`` value.
        flow_prompts_path (Optional[str]): Path to the flow-level
            prompts file, used to validate path-qualified refs. ``None``
            disables the validation.

    Returns:
        str: The key to look up in the flow-level prompts dict.

    Raises:
        ValueError: If the path-qualified ref points at a different
            file than ``flow_prompts_path``.
    """
    if "::" not in prompts_ref:
        return prompts_ref
    path_part, _, key_part = prompts_ref.rpartition("::")
    if flow_prompts_path is not None and path_part and path_part != flow_prompts_path:
        raise ValueError(
            f"prompts_ref {prompts_ref!r} points at a different prompts file "
            f"({path_part!r}) than the flow-level prompts file "
            f"({flow_prompts_path!r}). The runner wires exactly one prompts "
            "file per flow; move the entry into the flow-level file or "
            "reference it by bare key."
        )
    return key_part


def resolve_step_prompt(
    step: Any,
    prompts_file: Dict[str, Any],
    registry_entry: Any,
    flow_prompts_path: Optional[str] = None,
) -> Optional[ResolvedPrompt]:
    """Resolve the effective prompt for one processor.

    Precedence: inline :class:`PromptInline` > ``prompts_ref`` + overrides >
    ``prompts_ref`` alone > registry ``default_prompt_ref`` > ``None``.

    Args:
        step (Any): The :class:`src.flow_loader.ProcessorConfig`. Typed as
            ``Any`` to avoid a circular import; reads ``prompt``,
            ``prompts_ref``, and ``prompt_overrides``.
        prompts_file (Dict[str, Any]): Parsed ``config/prompts.json``.
        registry_entry (Any): The :class:`src.node_registry.NodeTypeEntry`
            for the processor's type.
        flow_prompts_path (Optional[str]): Path of the flow-level prompts
            file for path validation.

    Returns:
        Optional[ResolvedPrompt]: The resolved prompt, or ``None``.
    """
    inline_prompt = getattr(step, "prompt", None)
    prompts_ref = getattr(step, "prompts_ref", None)
    overrides = getattr(step, "prompt_overrides", None)

    if inline_prompt is not None and prompts_ref is not None:
        raise ValueError(
            "A step cannot set both inline 'prompt' and 'prompts_ref'. "
            "Use exactly one: inline for a full override, prompts_ref for "
            "a reference (with optional prompt_overrides)."
        )
    if overrides is not None and prompts_ref is None:
        raise ValueError(
            "'prompt_overrides' requires 'prompts_ref' to point at a base "
            "instruction list. Remove prompt_overrides or add prompts_ref."
        )

    if inline_prompt is not None:
        return ResolvedPrompt(
            instructions=list(inline_prompt.instructions),
            output_format=inline_prompt.output_format,
        )

    base_prompt_dict: Optional[Dict[str, Any]] = None
    if prompts_ref is not None:
        key = _extract_prompts_ref_key(prompts_ref, flow_prompts_path)
        if key not in prompts_file:
            raise KeyError(
                f"prompts_ref key {key!r} not found in flow-level prompts "
                f"file. Known keys: {sorted(prompts_file.keys())}"
            )
        base_prompt_dict = prompts_file[key] or {}
    else:
        default_ref = getattr(registry_entry, "default_prompt_ref", None)
        if default_ref is None:
            return None
        default_key = _extract_prompts_ref_key(default_ref, flow_prompts_path)
        if default_key not in prompts_file:
            return None
        base_prompt_dict = prompts_file[default_key] or {}

    base_instructions: List[str] = list(base_prompt_dict.get("instructions", []) or [])
    base_output_format: Optional[Any] = base_prompt_dict.get("output_format")

    final_instructions = base_instructions
    if overrides is not None and overrides.instructions is not None:
        instruction_delta = overrides.instructions
        if instruction_delta.replace is not None:
            final_instructions = list(instruction_delta.replace)
        if instruction_delta.prepend is not None:
            final_instructions = list(instruction_delta.prepend) + final_instructions
        if instruction_delta.append is not None:
            final_instructions = final_instructions + list(instruction_delta.append)

    return ResolvedPrompt(
        instructions=final_instructions,
        output_format=base_output_format,
    )
