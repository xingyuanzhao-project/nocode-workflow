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
"""Providers for which API keys can be configured at runtime."""


class ApiKeySetRequest(BaseModel):
    """Body of ``POST /api/settings/api-key``.

    Attributes:
        provider (ProviderName): Which provider this key belongs to.
        api_key (str): The raw API key string.
    """

    model_config = ConfigDict(extra="forbid")

    provider: ProviderName
    api_key: str


class ApiKeyTestRequest(BaseModel):
    """Body of ``POST /api/settings/api-key/test``.

    Attributes:
        provider (ProviderName): Which provider to test against.
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


class ProviderStatusResponse(BaseModel):
    """Response of ``GET /api/settings/providers``.

    Attributes:
        providers (List[ProviderStatusItem]): One entry per supported
            provider.
    """

    model_config = ConfigDict(extra="forbid")

    providers: List[ProviderStatusItem]
