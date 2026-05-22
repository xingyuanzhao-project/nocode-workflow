"""Routes under ``/api/settings`` — runtime API-key management.

Keys are stored in ``os.environ`` for the current server process only
and are NOT persisted to disk. A process restart clears them. This is
intentional: API keys are secrets and should come from ``.env`` or an
external secrets manager in production; the settings page is a
convenience for development and one-off sessions.

Contents and relationships
--------------------------

- :data:`router` — :class:`fastapi.APIRouter` exposing:

  - ``GET /api/settings/providers`` — list providers and whether a key
    is currently set.
  - ``POST /api/settings/api-key`` — set an API key for a provider.
  - ``POST /api/settings/api-key/test`` — validate a key against the
    provider without storing it.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.app` mounts :data:`router` alongside the other route
  modules.
"""

from __future__ import annotations

import os
from typing import Dict

import httpx
from fastapi import APIRouter, status

from server.schemas.settings import (
    ApiKeySetRequest,
    ApiKeyTestRequest,
    ApiKeyTestResponse,
    ProviderStatusItem,
    ProviderStatusResponse,
)


router = APIRouter(prefix="/api/settings", tags=["settings"])
"""Router exposing runtime API-key management endpoints."""


PROVIDER_ENV_VARS: Dict[str, str] = {
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
}
"""Mapping from provider name to the environment variable the flow
builder reads via ``api_key_env``."""

PROVIDER_AUTH_TEST_URLS: Dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1/auth/key",
    "openai": "https://api.openai.com/v1/models",
}
"""Endpoint per provider used to validate an API key.

OpenRouter's ``/api/v1/models`` is public (returns 200 regardless of
auth), so we use ``/api/v1/auth/key`` which returns key metadata on
success and 401/403 on invalid keys.  OpenAI's ``/v1/models`` already
requires auth and returns 401 on bad keys.
"""


@router.get("/providers", response_model=ProviderStatusResponse)
def list_providers() -> ProviderStatusResponse:
    """Return every supported provider and whether a key is set.

    Returns:
        ProviderStatusResponse: One entry per provider in
        :data:`PROVIDER_ENV_VARS`.
    """
    items = []
    for provider_name, env_var_name in sorted(PROVIDER_ENV_VARS.items()):
        current_value = os.environ.get(env_var_name, "")
        items.append(
            ProviderStatusItem(
                provider=provider_name,  # type: ignore[arg-type]
                configured=bool(current_value),
                env_var=env_var_name,
            )
        )
    return ProviderStatusResponse(providers=items)


@router.post(
    "/api-key",
    response_model=ProviderStatusResponse,
    status_code=status.HTTP_200_OK,
)
def set_api_key(request: ApiKeySetRequest) -> ProviderStatusResponse:
    """Store an API key in ``os.environ`` for the current session.

    The key is immediately available to any subsequent flow run in
    this server process. It is NOT written to ``.env`` or any other
    file.

    Args:
        request (ApiKeySetRequest): Provider and key to store.

    Returns:
        ProviderStatusResponse: Updated provider status list.
    """
    env_var_name = PROVIDER_ENV_VARS[request.provider]
    os.environ[env_var_name] = request.api_key
    return list_providers()


@router.post("/api-key/test", response_model=ApiKeyTestResponse)
async def test_api_key(request: ApiKeyTestRequest) -> ApiKeyTestResponse:
    """Validate an API key by calling an auth-gated provider endpoint.

    OpenRouter: ``GET /api/v1/auth/key`` — returns key metadata when
    valid, 401/403 when invalid.  OpenAI: ``GET /v1/models`` — returns
    the model catalogue when valid, 401 when invalid.

    Args:
        request (ApiKeyTestRequest): Provider and key to test.

    Returns:
        ApiKeyTestResponse: Validation result with a human-readable
        message.
    """
    auth_test_url = PROVIDER_AUTH_TEST_URLS[request.provider]
    headers = {"Authorization": f"Bearer {request.api_key}"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as http_client:
            response = await http_client.get(auth_test_url, headers=headers)
        if response.status_code == 200:
            return ApiKeyTestResponse(
                provider=request.provider,
                valid=True,
                message=f"{request.provider} key is valid.",
            )
        if response.status_code in (401, 403):
            return ApiKeyTestResponse(
                provider=request.provider,
                valid=False,
                message=f"{request.provider} rejected the key (HTTP {response.status_code}).",
            )
        return ApiKeyTestResponse(
            provider=request.provider,
            valid=False,
            message=(
                f"{request.provider} returned HTTP {response.status_code}. "
                "The key may be invalid or the service may be unavailable."
            ),
        )
    except httpx.RequestError as connection_error:
        return ApiKeyTestResponse(
            provider=request.provider,
            valid=False,
            message=f"Connection failed: {connection_error}",
        )
