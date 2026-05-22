"""Routes under ``/api/schema`` — node catalog and flow validation.

Contents and relationships
--------------------------

- :data:`router` — :class:`fastapi.APIRouter` exposing:
  ``GET /api/schema/node-types`` and ``POST /api/schema/validate``.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.app` mounts :data:`router` at the root so the full
  paths become ``/api/schema/...``.

Invariants enforced by this module
----------------------------------

- Handlers delegate to :class:`server.services.node_catalog.NodeCatalog`
  and :class:`server.services.flow_validation.FlowValidator`. No
  domain logic lives in this module.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from server.dependencies import get_flow_validator, get_node_catalog
from server.schemas.flow import FlowValidationRequest, FlowValidationResponse
from server.schemas.node_types import NodeTypeRegistryDTO
from server.services.flow_validation import FlowValidator
from server.services.node_catalog import NodeCatalog


router = APIRouter(prefix="/api/schema", tags=["schema"])
"""Router exposing node-catalog and validation endpoints."""


@router.get("/node-types", response_model=NodeTypeRegistryDTO)
def list_node_types(
    catalog: NodeCatalog = Depends(get_node_catalog),
) -> NodeTypeRegistryDTO:
    """Return the full node-type registry.

    Args:
        catalog (NodeCatalog): Injected node-catalog service.

    Returns:
        NodeTypeRegistryDTO: Registry contents reshaped for HTTP.
    """
    return catalog.list_entries()


@router.post("/validate", response_model=FlowValidationResponse)
def validate_flow(
    request: FlowValidationRequest,
    validator: FlowValidator = Depends(get_flow_validator),
) -> FlowValidationResponse:
    """Validate a raw flow dict against :class:`FlowSchema`.

    Args:
        request (FlowValidationRequest): Body containing the flow dict.
        validator (FlowValidator): Injected validation service.

    Returns:
        FlowValidationResponse: ``valid`` plus the error list.
    """
    return validator.validate(request.flow)
