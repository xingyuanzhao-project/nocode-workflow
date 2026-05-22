"""DTOs for the API-key management endpoints under ``/api/settings``.

Contents and relationships
--------------------------

- :class:`ApiKeySetRequest` — body of ``POST /api/settings/api-key``.
- :class:`ApiKeyTestRequest` — body of ``POST /api/settings/api-key/test``.
- :class:`ApiKeyTestResponse` — response confirming key validity.
- :class:`ProviderStatusItem` — per-provider key status entry.
- :class:`ProviderStatusResponse` — list response for
  ``GET /api/settings/providers``.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.routes.settings` uses these DTOs as FastAPI request
  and response models.
"""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, ConfigDict


ProviderName = Literal["openrouter", "openai"]
"""Cloud providers for which API keys can be configured at runtime."""

LocalProviderName = Literal["local_vllm", "ollama", "vllm", "llama_cpp"]
"""Local providers that connect via base URL without real API keys."""

AnyProviderName = Literal[
    "openrouter", "openai", "local_vllm", "ollama", "vllm", "llama_cpp",
]
"""Union of all supported provider identifiers."""


class ApiKeySetRequest(BaseModel):
    """Body of ``POST /api/settings/api-key``.

    Attributes:
        provider (ProviderName): Which cloud provider this key belongs to.
        api_key (str): The raw API key string.
    """

    model_config = ConfigDict(extra="forbid")

    provider: ProviderName
    api_key: str


class ApiKeyTestRequest(BaseModel):
    """Body of ``POST /api/settings/api-key/test``.

    Attributes:
        provider (ProviderName): Which cloud provider to test against.
        api_key (str): The raw API key to validate.
    """

    model_config = ConfigDict(extra="forbid")

    provider: ProviderName
    api_key: str


class ApiKeyTestResponse(BaseModel):
    """Response of ``POST /api/settings/api-key/test``.

    Attributes:
        provider (ProviderName): The tested provider.
        valid (bool): ``True`` if the key was accepted.
        message (str): Human-readable result summary.
    """

    model_config = ConfigDict(extra="forbid")

    provider: ProviderName
    valid: bool
    message: str


class LocalEndpointSetRequest(BaseModel):
    """Body of ``POST /api/settings/local-endpoint``.

    Attributes:
        provider (LocalProviderName): Which local provider backend.
        api_base (str): OpenAI-compatible base URL.
    """

    model_config = ConfigDict(extra="forbid")

    provider: LocalProviderName
    api_base: str


class LocalEndpointTestRequest(BaseModel):
    """Body of ``POST /api/settings/local-endpoint/test``.

    Attributes:
        api_base (str): Base URL to test (hits ``/models``).
    """

    model_config = ConfigDict(extra="forbid")

    api_base: str


class LocalEndpointTestResponse(BaseModel):
    """Response of ``POST /api/settings/local-endpoint/test``.

    Attributes:
        reachable (bool): ``True`` if the endpoint responded.
        models (List[str]): Model ids returned by the endpoint.
        message (str): Human-readable result summary.
    """

    model_config = ConfigDict(extra="forbid")

    reachable: bool
    models: List[str] = []
    message: str


class ProviderStatusItem(BaseModel):
    """Status of one provider's API key configuration.

    Attributes:
        provider (ProviderName): Provider identifier.
        configured (bool): ``True`` when an API key is currently set
            in the server's environment.
        env_var (str): Name of the environment variable that holds the
            key.
    """

    model_config = ConfigDict(extra="forbid")

    provider: ProviderName
    configured: bool
    env_var: str


class LocalEndpointStatusItem(BaseModel):
    """Status of one local endpoint configuration.

    Attributes:
        provider (LocalProviderName): Local provider identifier.
        api_base (str): Currently configured base URL.
        configured (bool): ``True`` when a custom URL has been set.
    """

    model_config = ConfigDict(extra="forbid")

    provider: LocalProviderName
    api_base: str
    configured: bool


class ProviderStatusResponse(BaseModel):
    """Response of ``GET /api/settings/providers``.

    Attributes:
        providers (List[ProviderStatusItem]): Cloud provider status.
        local_endpoints (List[LocalEndpointStatusItem]): Local endpoint
            status.
    """

    model_config = ConfigDict(extra="forbid")

    providers: List[ProviderStatusItem]
    local_endpoints: List[LocalEndpointStatusItem] = []
