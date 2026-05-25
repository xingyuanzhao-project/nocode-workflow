"""Routes under ``/api/flow/workflows`` — preset workflows.

Two endpoints live here:

- ``GET /api/flow/workflows`` — list every valid workflow.
- ``GET /api/flow/workflows/{workflow_id}`` — one workflow's full body.

Both endpoints are read-only; workflows are shipped with the repository
(under ``workflows/``), not user-created through the API.

Contents and relationships
--------------------------

- :data:`router` — :class:`fastapi.APIRouter` mounted at ``/api/flow``
  with path suffix ``/workflows``, matching the existing prefix used
  by :mod:`server.routes.flow`.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.app` mounts :data:`router` in :func:`create_app`.
- The GUI's ``NewFlowDialog`` component calls ``GET /api/flow/workflows``
  to render the picker and ``GET /api/flow/workflows/{id}`` to load the
  chosen workflow onto the canvas.

Invariants enforced by this module
----------------------------------

- Route handlers contain no domain logic; they only translate HTTP
  concerns. Domain logic lives in
  :class:`server.services.workflow_repository.WorkflowRepository`.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends

from server.dependencies import get_workflow_repository
from server.schemas.workflows import WorkflowDetail, WorkflowListItem
from server.services.workflow_repository import WorkflowRepository


router = APIRouter(prefix="/api/flow", tags=["workflows"])
"""Router exposing the preset workflow endpoints."""


@router.get("/workflows", response_model=List[WorkflowListItem])
def list_workflows(
    repository: WorkflowRepository = Depends(get_workflow_repository),
) -> List[WorkflowListItem]:
    """Return every valid preset workflow on disk.

    Args:
        repository (WorkflowRepository): Injected workflow repository.

    Returns:
        List[WorkflowListItem]: One entry per valid workflow,
        sorted by id.
    """
    return repository.list()


@router.get("/workflows/{workflow_id}", response_model=WorkflowDetail)
def get_workflow(
    workflow_id: str,
    repository: WorkflowRepository = Depends(get_workflow_repository),
) -> WorkflowDetail:
    """Return one workflow's id, label, description, and raw flow body.

    Args:
        workflow_id (str): YAML filename stem of the workflow.
        repository (WorkflowRepository): Injected workflow repository.

    Returns:
        WorkflowDetail: The workflow detail.
    """
    return repository.get(workflow_id)
