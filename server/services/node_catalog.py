"""Service that exposes the node-type registry over HTTP.

Thin wrapper around :mod:`src.node_registry`. The registry itself is a
process-wide singleton cached in :mod:`src.node_registry`; this service
only reshapes it into the HTTP DTOs declared by
:mod:`server.schemas.node_types`.

Contents and relationships
--------------------------

- :class:`NodeCatalog` — holds a reference to a
  :class:`src.node_registry.NodeTypeRegistry` and exposes one method
  :meth:`NodeCatalog.list_entries`.
- :func:`build_default_node_catalog` — convenience constructor used by
  the FastAPI dependency in :mod:`server.dependencies`.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.routes.schema` calls
  :meth:`NodeCatalog.list_entries` from the ``GET /api/schema/node-types``
  handler.

Invariants enforced by this module
----------------------------------

- Every :class:`src.node_registry.NodeTypeEntry` maps to exactly one
  :class:`server.schemas.node_types.NodeTypeEntryDTO`; field names
  match 1:1 so the conversion is mechanical.
"""

from __future__ import annotations

from src.node_registry import (
    NodeTypeEntry,
    NodeTypeRegistry,
    get_default_registry,
)

from server.schemas.node_types import NodeTypeEntryDTO, NodeTypeRegistryDTO


def _entry_to_dto(entry: NodeTypeEntry) -> NodeTypeEntryDTO:
    """Convert one registry row into its HTTP DTO.

    Args:
        entry (NodeTypeEntry): The registry row to convert.

    Returns:
        NodeTypeEntryDTO: A new DTO with field-for-field contents.
    """
    return NodeTypeEntryDTO(
        id=entry.id,
        category=entry.category,
        label=entry.label,
        description=entry.description,
        default_unit=entry.default_unit,
        consumes=list(entry.consumes),
        produces=list(entry.produces),
        llm_backed=entry.llm_backed,
        requires_resources=list(entry.requires_resources),
        default_io_schema=entry.default_io_schema,
        default_prompt_ref=entry.default_prompt_ref,
        default_group_by=entry.default_group_by,
    )


class NodeCatalog:
    """Read-only service exposing the node-type registry.

    Attributes:
        registry (NodeTypeRegistry): The wrapped
            :mod:`src.node_registry` registry.

    Methods:
        list_entries: Return the whole registry as a
            :class:`NodeTypeRegistryDTO`.
    """

    def __init__(self, registry: NodeTypeRegistry) -> None:
        """Store the registry this service exposes.

        Args:
            registry (NodeTypeRegistry): The registry instance, usually
                :func:`src.node_registry.get_default_registry`.
        """
        self.registry = registry

    def list_entries(self) -> NodeTypeRegistryDTO:
        """Return the registry reshaped into HTTP DTOs.

        Returns:
            NodeTypeRegistryDTO: One DTO per entry in
            :attr:`NodeCatalog.registry`.
        """
        return NodeTypeRegistryDTO(
            version=self.registry.version,
            entries=[_entry_to_dto(entry) for entry in self.registry.entries],
        )


def build_default_node_catalog() -> NodeCatalog:
    """Build a :class:`NodeCatalog` backed by the default registry.

    Returns:
        NodeCatalog: Service wrapping
        :func:`src.node_registry.get_default_registry`.
    """
    return NodeCatalog(get_default_registry())
