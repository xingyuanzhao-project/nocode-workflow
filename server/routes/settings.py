"""Routes under ``/api/settings`` — runtime API-key and endpoint management.

Cloud API keys are persisted to the project-root ``.env`` file so that
both the FastAPI server process and the Celery worker process can read
them. The keys are also set in ``os.environ`` for immediate use by the
server process. Local endpoint URLs are stored in a module-level dict
that survives for the process lifetime but not across restarts.

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
from pathlib import Path
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
    "claude": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
}
"""Cloud provider name to environment variable mapping."""

PROVIDER_AUTH_TEST_URLS: Dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1/auth/key",
    "openai": "https://api.openai.com/v1/models",
    "claude": "https://api.anthropic.com/v1/models",
    "google": "https://generativelanguage.googleapis.com/v1beta/models",
}
"""Auth-gated endpoint per cloud provider for key validation."""

LOCAL_ENDPOINT_ENV_VARS: Dict[str, str] = {
    "ollama": "OLLAMA_API_BASE",
    "vllm": "VLLM_API_BASE",
    "llama_cpp": "LLAMA_CPP_API_BASE",
}
"""Environment variable names that persist the user-configured local URLs."""


def _get_local_endpoints() -> List[LocalEndpointStatusItem]:
    """Build the local endpoint status list."""
    items = []
    for provider_name in sorted(LOCAL_ENDPOINT_ENV_VARS):
        env_var = LOCAL_ENDPOINT_ENV_VARS[provider_name]
        configured_url = os.environ.get(env_var, "").strip()
        items.append(
            LocalEndpointStatusItem(
                provider=provider_name,  # type: ignore[arg-type]
                api_base=configured_url,
                configured=bool(configured_url),
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
    cloud_provider_order = ["openrouter", "openai", "claude", "google"]
    for provider_name in cloud_provider_order:
        env_var_name = PROVIDER_ENV_VARS[provider_name]
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


_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
"""Project root directory (grandparent of server/routes/)."""


def _persist_env_var_to_dotenv(var_name: str, var_value: str) -> None:
    """Write or update a variable in the project-root ``.env`` file.

    If the variable already exists in the file, its value is replaced
    in-place. Otherwise a new line is appended. This ensures the Celery
    worker (which reads ``.env`` at task start via
    :func:`src.flow_builder._load_dotenv_into_environ`) sees the key.
    """
    env_path = _PROJECT_ROOT / ".env"
    lines: list[str] = []
    found = False
    if env_path.exists():
        with env_path.open("r", encoding="utf-8") as fh:
            for raw_line in fh:
                stripped = raw_line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    key_part = stripped.partition("=")[0].strip()
                    if key_part == var_name:
                        lines.append(f"{var_name}={var_value}\n")
                        found = True
                        continue
                lines.append(raw_line if raw_line.endswith("\n") else raw_line + "\n")
    if not found:
        lines.append(f"{var_name}={var_value}\n")
    with env_path.open("w", encoding="utf-8") as fh:
        fh.writelines(lines)


@router.post(
    "/api-key",
    response_model=ProviderStatusResponse,
    status_code=status.HTTP_200_OK,
)
def set_api_key(request: ApiKeySetRequest) -> ProviderStatusResponse:
    """Store a cloud API key in ``os.environ`` and persist to ``.env``.

    The key is written to the project-root ``.env`` file so the Celery
    worker can read it at task start. It is also set in ``os.environ``
    for immediate use by the server process.

    Args:
        request (ApiKeySetRequest): Provider and key to store.

    Returns:
        ProviderStatusResponse: Updated status list.
    """
    env_var_name = PROVIDER_ENV_VARS[request.provider]
    os.environ[env_var_name] = request.api_key
    _persist_env_var_to_dotenv(env_var_name, request.api_key)
    return list_providers()


def _build_test_request(
    provider: str, api_key: str
) -> tuple[str, Dict[str, str]]:
    """Return (url, headers) for the provider's key-validation request.

    Anthropic uses ``x-api-key`` + ``anthropic-version`` headers.
    Google uses a ``key`` query parameter.
    All others use a standard Bearer token.
    """
    base_url = PROVIDER_AUTH_TEST_URLS[provider]
    if provider == "claude":
        return base_url, {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
    if provider == "google":
        return f"{base_url}?key={api_key}", {}
    return base_url, {"Authorization": f"Bearer {api_key}"}


@router.post("/api-key/test", response_model=ApiKeyTestResponse)
async def test_api_key(request: ApiKeyTestRequest) -> ApiKeyTestResponse:
    """Validate a cloud API key against the provider's auth endpoint.

    Args:
        request (ApiKeyTestRequest): Provider and key to test.

    Returns:
        ApiKeyTestResponse: Validation result.
    """
    test_url, headers = _build_test_request(request.provider, request.api_key)
    try:
        async with httpx.AsyncClient(timeout=15.0) as http_client:
            response = await http_client.get(test_url, headers=headers)
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
    """Store a local endpoint URL in ``os.environ`` and persist to ``.env``.

    Args:
        request (LocalEndpointSetRequest): Provider and base URL.

    Returns:
        ProviderStatusResponse: Updated status list.
    """
    env_var = LOCAL_ENDPOINT_ENV_VARS[request.provider]
    value = request.api_base.rstrip("/")
    os.environ[env_var] = value
    _persist_env_var_to_dotenv(env_var, value)
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
