"""HTTP DTOs for the node-type catalog endpoint.

Mirror :class:`src.node_registry.NodeTypeEntry` and
:class:`src.node_registry.NodeTypeRegistry` but kept separate so
HTTP-only presentation fields can be added later without touching the
domain models.

Contents and relationships
--------------------------

- :class:`NodeTypeEntryDTO` — wire shape for one registry entry.
- :class:`NodeTypeRegistryDTO` — wire shape for the full registry
  returned by ``GET /api/schema/node-types``.

How the rest of the system uses this module
-------------------------------------------

- :class:`server.services.node_catalog.NodeCatalog` converts the
  :mod:`src.node_registry` objects into these DTOs.
- :mod:`server.routes.schema` returns the
  :class:`NodeTypeRegistryDTO` as the response body.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class NodeTypeEntryDTO(BaseModel):
    """One node-type registry row, flattened for HTTP transport.

    Attributes:
        id (str): Stable identifier; the value users write under
            ``steps[*].type`` for processor nodes.
        category (str): ``"data"``, ``"processor"``, or ``"resource"``.
        label (str): Short human-readable name suitable for a GUI
            palette entry.
        description (str): Longer human-readable description.
        default_unit (Optional[str]): Default value the flow loader uses
            when a step of this type omits ``unit``.
        consumes (List[str]): Names of fields this node reads from the
            pipeline context.
        produces (List[str]): Names of fields this node writes into the
            pipeline context.
        llm_backed (bool): ``True`` when the node issues LLM calls at
            runtime.
        requires_resources (List[str]): Resource kinds this node needs
            at runtime.
        default_io_schema (Optional[Dict[str, Any]]): Default
            ``io_schema`` dict shape used when the step does not supply
            its own.
        default_prompt_ref (Optional[str]): Default ``prompts_ref``
            pointer used when the step does not supply its own.
        default_group_by (Optional[str]): Default ``group_by`` value
            used when the step omits it.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    category: str
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


class NodeTypeRegistryDTO(BaseModel):
    """Whole node-type registry, as returned by the catalog endpoint.

    Attributes:
        version (int): Registry file format version.
        entries (List[NodeTypeEntryDTO]): One DTO per registry row.
    """

    model_config = ConfigDict(extra="forbid")

    version: int = 1
    entries: List[NodeTypeEntryDTO] = Field(default_factory=list)
