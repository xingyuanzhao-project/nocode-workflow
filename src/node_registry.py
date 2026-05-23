"""Registry of node types consumed by the config-driven flow runner.

The registry lives on disk as ``config/node_types.yaml``. Each entry declares
one node type (a data source, a processor step, or a resource) together with
the defaults that other modules need to know about it: which unit of analysis
the node operates on, what it consumes and produces, whether it needs an LLM
client, and what its default I/O schema and default prompt reference are.

Contents and relationships
--------------------------

- :class:`NodeTypeCategory` — closed enum identifying which family a node
  belongs to (``data``, ``processor``, ``resource``).
- :class:`NodeTypeEntry` — one row of the registry. Carries the fields that
  :mod:`src.flow_loader` and :mod:`src.flow_builder` read when they validate
  a step type and resolve its I/O schema and prompt defaults.
- :class:`NodeTypeRegistry` — the whole registry as a validated Pydantic
  model. Exposes :meth:`NodeTypeRegistry.get_entry` and
  :meth:`NodeTypeRegistry.processor_step_types` helpers used by callers.
- :data:`DEFAULT_REGISTRY_PATH` — the canonical path
  ``config/node_types.yaml`` relative to the project root. Kept as the
  single source of truth so tests and the production runner agree on what
  is loaded.

How the rest of the system uses this module
-------------------------------------------

:mod:`src.flow_loader` calls :func:`get_processor_step_types` inside
:meth:`src.flow_loader.StepConfig.validate_type` to accept exactly the step
``type`` values declared under ``category: processor`` in the YAML. This
replaces the previously hardcoded ``STEP_TYPES`` frozenset.

:mod:`src.flow_builder` calls :func:`get_entry` from the per-step config
builder to read ``default_io_schema`` and ``default_prompt_ref`` when the
user has not supplied an override on the :class:`StepConfig` itself.

Invariants enforced by this module
----------------------------------

- Every entry has a unique :attr:`NodeTypeEntry.id`; duplicates raise at
  load time.
- Every entry's :attr:`NodeTypeEntry.category` is one of the members of
  :class:`NodeTypeCategory`.
- ``llm_backed`` implies ``"llm_provider"`` appears in
  :attr:`NodeTypeEntry.requires_resources`; load-time validation rejects
  inconsistent entries.
- ``default_io_schema`` is either ``None`` or a dict shaped as
  ``{"input": {...}, "output": {...}}`` — the same shape validated by
  :class:`src.io_schema.IOSchema`. The registry itself does not import
  :mod:`src.io_schema` to avoid a circular import; shape compliance is
  only enforced when the field is actually consumed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


NodeTypeCategory = Literal["data", "processor", "resource"]
"""Closed set of node families the registry recognises.

``data`` nodes represent inputs such as CSV files. ``processor`` nodes
represent LLM-backed steps dispatched by :class:`src.flow_builder.FlowRunner`.
``resource`` nodes represent clients such as an LLM provider endpoint.
"""


DEFAULT_REGISTRY_PATH: Path = (
    Path(__file__).resolve().parent.parent / "config" / "node_types.yaml"
)
"""Canonical on-disk location of the registry YAML relative to project root."""


class NodeTypeEntry(BaseModel):
    """One entry in the node type registry.

    Attributes:
        id (str): Stable identifier referenced from flow YAML files. For
            processor nodes this is the value users write under
            ``steps[*].type`` (for example ``"single_summary"`` or
            ``"classification"``).
        category (NodeTypeCategory): Which family the node belongs to.
        label (str): Short human-readable name, suitable for a GUI palette
            entry.
        description (str): Longer human-readable description.
        default_unit (Optional[str]): Always ``"row"`` for processors,
            ``None`` for data and resource nodes.
        consumes (List[str]): Names of fields this node reads from the
            pipeline context. Informational for now; used by the future
            GUI edge validator.
        produces (List[str]): Names of fields this node writes into the
            pipeline context. Informational for now; used by the future
            GUI edge validator.
        llm_backed (bool): ``True`` when the node issues LLM calls at
            runtime. Used by the builder to decide whether a resolved LLM
            client must be wired into the processor.
        requires_resources (List[str]): Resource kinds this node needs at
            runtime (for example ``"llm_provider"``).
        default_io_schema (Optional[Dict[str, Any]]): Default ``io_schema``
            dict shape (``{"input": {...}, "output": {...}}``) used when
            the step does not supply its own. ``None`` when no default
            exists (data and resource nodes).
        default_prompt_ref (Optional[str]): Default ``prompts_ref``
            pointer (shape ``"path::key"`` or bare ``"key"``) used when
            the step does not supply its own. ``None`` when no default
            exists.
        default_group_by (Optional[str]): Deprecated, ignored.

    Methods:
        ensure_llm_backed_requires_provider: Enforce the cross-field
            invariant that :attr:`llm_backed` entries declare
            ``llm_provider`` in :attr:`requires_resources`.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    category: NodeTypeCategory
    label: str = ""
    description: str = ""
    default_unit: Optional[str] = None
    consumes: List[str] = Field(default_factory=list)
    produces: List[str] = Field(default_factory=list)
    llm_backed: bool = False
    requires_resources: List[str] = Field(default_factory=list)
    default_io_schema: Optional[Dict[str, Any]] = None
    default_prompt_ref: Optional[str] = None
    default_group_by: Optional[str] = None

    @model_validator(mode="after")
    def ensure_llm_backed_requires_provider(self) -> "NodeTypeEntry":
        """Reject ``llm_backed`` entries that omit the ``llm_provider`` resource.

        Returns:
            NodeTypeEntry: The same instance, unchanged.

        Raises:
            ValueError: If :attr:`llm_backed` is ``True`` but
                ``"llm_provider"`` is absent from
                :attr:`requires_resources`.
        """
        if self.llm_backed and "llm_provider" not in self.requires_resources:
            raise ValueError(
                f"Node type {self.id!r} declares llm_backed=True but does "
                "not list 'llm_provider' in requires_resources. Add it to "
                "requires_resources or set llm_backed to False."
            )
        return self


class NodeTypeRegistry(BaseModel):
    """Whole node type registry as a validated Pydantic model.

    Attributes:
        version (int): Version of the registry file format. Incremented
            when the registry schema changes in an incompatible way.
        entries (List[NodeTypeEntry]): All registered node types.

    Methods:
        ensure_unique_entry_ids: Reject registries with duplicate entry
            ids.
        get_entry: Look up a registry row by id.
        processor_step_types: Return the frozenset of processor step
            ids, used by :mod:`src.flow_loader` for step-type validation.
    """

    model_config = ConfigDict(extra="forbid")

    version: int = 1
    entries: List[NodeTypeEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def ensure_unique_entry_ids(self) -> "NodeTypeRegistry":
        """Reject registries that contain duplicate entry ids.

        Returns:
            NodeTypeRegistry: The same instance, unchanged.

        Raises:
            ValueError: If two entries share the same :attr:`NodeTypeEntry.id`.
        """
        seen_ids: set[str] = set()
        for entry in self.entries:
            if entry.id in seen_ids:
                raise ValueError(
                    f"Duplicate node type entry id: {entry.id!r}. "
                    "Every registry entry must have a unique id."
                )
            seen_ids.add(entry.id)
        return self

    def get_entry(self, entry_id: str) -> NodeTypeEntry:
        """Return the registry entry whose id matches ``entry_id``.

        Args:
            entry_id (str): The :attr:`NodeTypeEntry.id` to look up.

        Returns:
            NodeTypeEntry: The matching entry.

        Raises:
            KeyError: If no entry has the requested id.
        """
        for entry in self.entries:
            if entry.id == entry_id:
                return entry
        raise KeyError(
            f"Node type {entry_id!r} is not registered. Known ids: "
            f"{sorted(e.id for e in self.entries)}"
        )

    def processor_step_types(self) -> FrozenSet[str]:
        """Return the set of ids whose :attr:`NodeTypeEntry.category` is ``processor``.

        Returns:
            FrozenSet[str]: Exactly the step-type values accepted by
            :class:`src.flow_loader.StepConfig.validate_type`.
        """
        return frozenset(
            entry.id for entry in self.entries if entry.category == "processor"
        )


def load_registry(registry_yaml_path: Path) -> NodeTypeRegistry:
    """Load a :class:`NodeTypeRegistry` from a YAML file on disk.

    Args:
        registry_yaml_path (Path): Path to the registry YAML file.

    Returns:
        NodeTypeRegistry: The parsed and validated registry.

    Raises:
        FileNotFoundError: If ``registry_yaml_path`` does not exist.
        ValueError: If YAML parsing or Pydantic validation fails.
    """
    registry_yaml_path = Path(registry_yaml_path)
    if not registry_yaml_path.exists():
        raise FileNotFoundError(
            f"Node type registry YAML not found: {registry_yaml_path}"
        )
    with registry_yaml_path.open("r", encoding="utf-8") as yaml_file:
        raw_document: Dict[str, Any] = yaml.safe_load(yaml_file) or {}
    return NodeTypeRegistry(**raw_document)


_REGISTRY_SINGLETON: Optional[NodeTypeRegistry] = None
"""Lazily populated in-process cache of the registry loaded from
:data:`DEFAULT_REGISTRY_PATH`. Reset by :func:`reset_default_registry_cache`
for tests that need to rebuild the cache after patching the file."""


def get_default_registry() -> NodeTypeRegistry:
    """Return the process-wide cached registry from :data:`DEFAULT_REGISTRY_PATH`.

    The first call loads and validates the file on disk; subsequent calls
    return the same object. Tests that mutate the on-disk file should call
    :func:`reset_default_registry_cache` to force a reload.

    Returns:
        NodeTypeRegistry: The cached registry.

    Raises:
        FileNotFoundError: If :data:`DEFAULT_REGISTRY_PATH` does not
            exist.
        ValueError: If the file is not valid under
            :class:`NodeTypeRegistry`.
    """
    global _REGISTRY_SINGLETON
    if _REGISTRY_SINGLETON is None:
        _REGISTRY_SINGLETON = load_registry(DEFAULT_REGISTRY_PATH)
    return _REGISTRY_SINGLETON


def reset_default_registry_cache() -> None:
    """Clear the cached default registry so the next call reloads from disk.

    Intended for tests that modify :data:`DEFAULT_REGISTRY_PATH` or want a
    guaranteed fresh read. Has no effect on already-loaded non-default
    registries.
    """
    global _REGISTRY_SINGLETON
    _REGISTRY_SINGLETON = None


def get_processor_step_types(
    registry: Optional[NodeTypeRegistry] = None,
) -> FrozenSet[str]:
    """Return the processor step-type ids from ``registry`` (default cached).

    Thin wrapper around :meth:`NodeTypeRegistry.processor_step_types` kept
    as a module-level function so callers that do not need to touch the
    registry object can import a single symbol.

    Args:
        registry (Optional[NodeTypeRegistry]): Registry to query. Defaults
            to :func:`get_default_registry`.

    Returns:
        FrozenSet[str]: The processor step-type ids.
    """
    if registry is None:
        registry = get_default_registry()
    return registry.processor_step_types()


def get_entry(
    step_type: str,
    registry: Optional[NodeTypeRegistry] = None,
) -> NodeTypeEntry:
    """Return the registry entry for ``step_type`` from ``registry`` (default cached).

    Thin wrapper around :meth:`NodeTypeRegistry.get_entry`.

    Args:
        step_type (str): The :attr:`NodeTypeEntry.id` to look up.
        registry (Optional[NodeTypeRegistry]): Registry to query. Defaults
            to :func:`get_default_registry`.

    Returns:
        NodeTypeEntry: The matching entry.

    Raises:
        KeyError: If no entry has the requested id.
    """
    if registry is None:
        registry = get_default_registry()
    return registry.get_entry(step_type)
