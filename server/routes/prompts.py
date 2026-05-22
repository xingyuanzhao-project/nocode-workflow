"""Routes under ``/api/prompts`` — read-only prompts registry.

One endpoint lives here: ``GET /api/prompts`` returns the parsed
``config/prompts.json`` so the GUI's Prompt tab can populate its
prompt-key dropdown and placeholder reference sidebar without
re-parsing the file in the browser.

Contents and relationships
--------------------------

- :data:`router` — :class:`fastapi.APIRouter` mounted at ``/api``
  with the ``prompts`` suffix so the full path is ``/api/prompts``.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.app` mounts :data:`router` in :func:`create_app`.
- The GUI's ``PromptTab`` component calls ``GET /api/prompts`` once
  when the property panel opens and caches the result via TanStack
  Query.

Invariants enforced by this module
----------------------------------

- The handler contains no domain logic; it delegates to
  :class:`server.services.prompts_repository.PromptsRepository`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from server.dependencies import get_prompts_repository
from server.schemas.prompts import PromptsResponse
from server.services.prompts_repository import PromptsRepository


router = APIRouter(prefix="/api", tags=["prompts"])
"""Router exposing the prompts-registry endpoint."""


@router.get("/prompts", response_model=PromptsResponse)
def get_prompts_registry(
    repository: PromptsRepository = Depends(get_prompts_repository),
) -> PromptsResponse:
    """Return the parsed ``config/prompts.json`` as JSON.

    Args:
        repository (PromptsRepository): Injected prompts repository.

    Returns:
        PromptsResponse: File path and a dict of ``prompt_key ->
        PromptEntry``.
    """
    return repository.read()
