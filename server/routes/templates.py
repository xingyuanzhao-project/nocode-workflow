"""Routes under ``/api/flow/templates`` — preset flow templates.

Two endpoints live here:

- ``GET /api/flow/templates`` — list every valid template.
- ``GET /api/flow/templates/{template_id}`` — one template's full body.

Both endpoints are read-only; templates are shipped with the repository
(under ``config/templates/``), not user-created through the API.

Contents and relationships
--------------------------

- :data:`router` — :class:`fastapi.APIRouter` mounted at ``/api/flow``
  with path suffix ``/templates``, matching the existing prefix used
  by :mod:`server.routes.flow`.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.app` mounts :data:`router` in :func:`create_app`.
- The GUI's ``NewFlowDialog`` component calls ``GET /api/flow/templates``
  to render the picker and ``GET /api/flow/templates/{id}`` to load the
  chosen template onto the canvas.

Invariants enforced by this module
----------------------------------

- Route handlers contain no domain logic; they only translate HTTP
  concerns. Domain logic lives in
  :class:`server.services.template_repository.TemplateRepository`.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends

from server.dependencies import get_template_repository
from server.schemas.templates import FlowTemplateDetail, FlowTemplateListItem
from server.services.template_repository import TemplateRepository


router = APIRouter(prefix="/api/flow", tags=["templates"])
"""Router exposing the preset flow-template endpoints."""


@router.get("/templates", response_model=List[FlowTemplateListItem])
def list_templates(
    repository: TemplateRepository = Depends(get_template_repository),
) -> List[FlowTemplateListItem]:
    """Return every valid preset template on disk.

    Args:
        repository (TemplateRepository): Injected template repository.

    Returns:
        List[FlowTemplateListItem]: One entry per valid template,
        sorted by id.
    """
    return repository.list()


@router.get("/templates/{template_id}", response_model=FlowTemplateDetail)
def get_template(
    template_id: str,
    repository: TemplateRepository = Depends(get_template_repository),
) -> FlowTemplateDetail:
    """Return one template's id, label, description, and raw flow body.

    Args:
        template_id (str): YAML filename stem of the template.
        repository (TemplateRepository): Injected template repository.

    Returns:
        FlowTemplateDetail: The template detail.
    """
    return repository.get(template_id)
