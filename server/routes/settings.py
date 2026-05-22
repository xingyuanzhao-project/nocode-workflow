"""Routes under ``/api/settings`` — runtime API-key and endpoint management.

Cloud API keys are stored in ``os.environ`` for the current server
process only and are NOT persisted to disk. Local endpoint URLs are
stored in a module-level dict that survives for the process lifetime
but not across restarts.

Contents and relationships
--------------------------

- :data:`router` — :class:`fastapi.APIRouter` exposing cloud key and
  local endpoint management endpoints.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.app` mounts :data:`router` alongside the other route
  modules.
"""

from __future__ import annotations

import os
from typing import Dict, List

import httpx
from fastapi import APIRouter, status

from server.schemas.settings import (
    ApiKeySetRequest,
    ApiKeyTestRequest,
    ApiKeyTestResponse,
    LocalEndpointSetRequest,
    LocalEndpointStatusItem,
    LocalEndpointTestRequest,
    LocalEndpointTestResponse,
    ProviderStatusItem,
    ProviderStatusResponse,
)


router = APIRouter(prefix="/api/settings", tags=["settings"])
"""Router exposing runtime API-key and local-endpoint management."""


PROVIDER_ENV_VARS: Dict[str, str] = {
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
}
"""Cloud provider name to environment variable mapping."""

PROVIDER_AUTH_TEST_URLS: Dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1/auth/key",
    "openai": "https://api.openai.com/v1/models",
}
"""Auth-gated endpoint per cloud provider for key validation."""

LOCAL_ENDPOINT_DEFAULTS: Dict[str, str] = {
    "local_vllm": "http://localhost:8000/v1",
    "ollama": "http://localhost:11434/v1",
    "vllm": "http://localhost:8000/v1",
    "llama_cpp": "http://localhost:8080/v1",
}
"""Default base URLs per local provider."""

_local_endpoint_overrides: Dict[str, str] = {}
"""Session-scoped URL overrides for local providers set via the API."""


def _get_local_endpoints() -> List[LocalEndpointStatusItem]:
    """Build the local endpoint status list."""
    items = []
    for provider_name, default_url in sorted(LOCAL_ENDPOINT_DEFAULTS.items()):
        override = _local_endpoint_overrides.get(provider_name)
        items.append(
            LocalEndpointStatusItem(
                provider=provider_name,  # type: ignore[arg-type]
                api_base=override or default_url,
                configured=provider_name in _local_endpoint_overrides,
            )
        )
    return items


@router.get("/providers", response_model=ProviderStatusResponse)
def list_providers() -> ProviderStatusResponse:
    """Return cloud provider key status and local endpoint status.

    Returns:
        ProviderStatusResponse: Cloud and local provider status.
    """
    cloud_items = []
    for provider_name, env_var_name in sorted(PROVIDER_ENV_VARS.items()):
        current_value = os.environ.get(env_var_name, "")
        cloud_items.append(
            ProviderStatusItem(
                provider=provider_name,  # type: ignore[arg-type]
                configured=bool(current_value),
                env_var=env_var_name,
            )
        )
    return ProviderStatusResponse(
        providers=cloud_items,
        local_endpoints=_get_local_endpoints(),
    )


@router.post(
    "/api-key",
    response_model=ProviderStatusResponse,
    status_code=status.HTTP_200_OK,
)
def set_api_key(request: ApiKeySetRequest) -> ProviderStatusResponse:
    """Store a cloud API key in ``os.environ`` for the current session.

    Args:
        request (ApiKeySetRequest): Provider and key to store.

    Returns:
        ProviderStatusResponse: Updated status list.
    """
    env_var_name = PROVIDER_ENV_VARS[request.provider]
    os.environ[env_var_name] = request.api_key
    return list_providers()


@router.post("/api-key/test", response_model=ApiKeyTestResponse)
async def test_api_key(request: ApiKeyTestRequest) -> ApiKeyTestResponse:
    """Validate a cloud API key against the provider's auth endpoint.

    Args:
        request (ApiKeyTestRequest): Provider and key to test.

    Returns:
        ApiKeyTestResponse: Validation result.
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


@router.post(
    "/local-endpoint",
    response_model=ProviderStatusResponse,
    status_code=status.HTTP_200_OK,
)
def set_local_endpoint(
    request: LocalEndpointSetRequest,
) -> ProviderStatusResponse:
    """Store a local endpoint URL for the current session.

    Args:
        request (LocalEndpointSetRequest): Provider and base URL.

    Returns:
        ProviderStatusResponse: Updated status list.
    """
    _local_endpoint_overrides[request.provider] = request.api_base.rstrip("/")
    return list_providers()


def _rewrite_localhost_for_docker(url: str) -> str:
    """Replace ``localhost`` with ``host.docker.internal`` when running
    inside a Docker container, so the backend can reach services on
    the host machine."""
    import platform

    if platform.system() == "Linux":
        return url.replace("://localhost", "://host.docker.internal").replace(
            "://127.0.0.1", "://host.docker.internal"
        )
    return url


@router.post("/local-endpoint/test", response_model=LocalEndpointTestResponse)
async def test_local_endpoint(
    request: LocalEndpointTestRequest,
) -> LocalEndpointTestResponse:
    """Test a local endpoint by hitting its ``/models`` path.

    Compatible with Ollama, vLLM, and llama.cpp servers that expose
    an OpenAI-compatible ``GET /models`` endpoint. When running inside
    Docker, ``localhost`` URLs are rewritten to ``host.docker.internal``
    so the container can reach the host machine.

    Args:
        request (LocalEndpointTestRequest): Base URL to test.

    Returns:
        LocalEndpointTestResponse: Reachability and model list.
    """
    base = _rewrite_localhost_for_docker(request.api_base.rstrip("/"))
    models_url = f"{base}/models"
    try:
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            response = await http_client.get(
                models_url,
                headers={"Authorization": "Bearer dummy"},
            )
        if response.status_code == 200:
            body = response.json()
            model_ids: List[str] = []
            if isinstance(body, dict) and "data" in body:
                for entry in body["data"]:
                    if isinstance(entry, dict) and "id" in entry:
                        model_ids.append(str(entry["id"]))
            return LocalEndpointTestResponse(
                reachable=True,
                models=model_ids,
                message=(
                    f"Connected. Found {len(model_ids)} model(s): "
                    f"{', '.join(model_ids[:5]) or 'none listed'}."
                ),
            )
        return LocalEndpointTestResponse(
            reachable=False,
            models=[],
            message=f"Endpoint returned HTTP {response.status_code}.",
        )
    except httpx.RequestError as connection_error:
        return LocalEndpointTestResponse(
            reachable=False,
            models=[],
            message=f"Connection failed: {connection_error}",
        )
