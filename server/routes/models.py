"""Routes under ``/api/models`` — provider model-list proxy.

One endpoint lives here: ``GET /api/models/{provider}`` returns the
cached (or freshly fetched) model list for one LLM provider. The
provider name is validated by the
:class:`server.schemas.models.ProviderName` enum; unknown providers
return 422 (FastAPI's default enum rejection).

Contents and relationships
--------------------------

- :data:`router` — :class:`fastapi.APIRouter` mounted at ``/api``
  with the ``models/{provider}`` suffix so the full path is
  ``/api/models/{provider}``.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.app` mounts :data:`router` in :func:`create_app`.
- The GUI's ``LLMProviderNode`` component calls
  ``GET /api/models/{provider}`` when the provider selector changes.

Invariants enforced by this module
----------------------------------

- The handler contains no domain logic; it delegates to
  :class:`server.services.model_list_proxy.ModelListProxy.read`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from server.dependencies import get_model_list_proxy
from server.schemas.models import ProviderModelsResponse, ProviderName
from server.services.model_list_proxy import ModelListProxy


router = APIRouter(prefix="/api", tags=["models"])
"""Router exposing the provider model-list proxy endpoint."""


@router.get("/models/{provider}", response_model=ProviderModelsResponse)
async def get_provider_models(
    provider: ProviderName,
    proxy: ModelListProxy = Depends(get_model_list_proxy),
) -> ProviderModelsResponse:
    """Return the cached (or freshly fetched) model list for ``provider``.

    Args:
        provider (ProviderName): Which upstream to query.
        proxy (ModelListProxy): Injected proxy service.

    Returns:
        ProviderModelsResponse: Normalised model entries plus the
        timestamp the cache was populated.
    """
    return await proxy.read(provider)
