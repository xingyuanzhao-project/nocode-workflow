"""Provider model-list proxy with a Redis-backed cache.

Every time the GUI's ``LLMProviderNode`` opens its model picker, it
calls ``GET /api/models/{provider}``. This service answers from a
Redis cache with a 10-minute TTL; on miss it fetches the upstream
catalogue with :class:`httpx.AsyncClient` and repopulates the cache.
The cache key is ``f"{redis_key_prefix}:models:{provider}"`` so it
sits next to the application's other Redis keys without colliding
with Celery-managed keys.

Contents and relationships
--------------------------

- :class:`ModelListProxy` — the service.
- :data:`MODEL_CACHE_TTL_SECONDS` — the fixed 10-minute TTL declared
  in the plan.
- :data:`_OPENROUTER_MODELS_URL` / :data:`_OPENAI_MODELS_URL` —
  upstream endpoints.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.routes.models` calls :meth:`ModelListProxy.read` from
  ``GET /api/models/{provider}``.
- :mod:`server.dependencies` exposes the singleton via
  ``request.app.state.model_list_proxy``, constructed once in
  :func:`server.app.create_app` with the application Redis client and
  an ``httpx.AsyncClient`` owned by the FastAPI app.

Invariants enforced by this module
----------------------------------

- Every cache write sets ``EX=MODEL_CACHE_TTL_SECONDS``. Cache reads
  therefore always return data at most 10 minutes old.
- The cache stores the serialised
  :class:`server.schemas.models.ProviderModelsResponse` JSON string
  (not the raw upstream response) so cache reads skip upstream-shape
  normalisation.
- OpenAI requires an API key; the proxy reads it from the process
  environment (``OPENAI_API_KEY``) at call time so a missing key only
  fails the OpenAI branch, not OpenRouter.
- Upstream errors are translated into :class:`ValueError` / :class:`FileNotFoundError`
  so :mod:`server.errors` surfaces them as 400 / 404 rather than
  leaking an :class:`httpx.HTTPError` to the client.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx
import redis

from server.schemas.models import (
    ProviderModel,
    ProviderModelsResponse,
    ProviderName,
)


MODEL_CACHE_TTL_SECONDS: int = 600
"""10-minute TTL applied to every ``models:{provider}`` cache entry.

The GUI refreshes the model list only on dialog open, so a stale list
is acceptable for this window and avoids calling the provider on
every keystroke.
"""


_OPENROUTER_MODELS_URL: str = "https://openrouter.ai/api/v1/models"
"""Upstream endpoint for OpenRouter's public model catalogue."""


_OPENAI_MODELS_URL: str = "https://api.openai.com/v1/models"
"""Upstream endpoint for OpenAI's authenticated model catalogue."""


_ANTHROPIC_MODELS_URL: str = "https://api.anthropic.com/v1/models"
"""Upstream endpoint for Anthropic's model catalogue."""


_GOOGLE_MODELS_URL: str = (
    "https://generativelanguage.googleapis.com/v1beta/models"
)
"""Upstream endpoint for Google's Gemini model catalogue."""


_OPENAI_API_KEY_ENV_VAR: str = "OPENAI_API_KEY"
"""Environment variable consulted for the OpenAI Bearer token."""

_ANTHROPIC_API_KEY_ENV_VAR: str = "ANTHROPIC_API_KEY"
"""Environment variable consulted for the Anthropic API key."""

_GOOGLE_API_KEY_ENV_VAR: str = "GOOGLE_API_KEY"
"""Environment variable consulted for the Google API key."""


_LOCAL_PROVIDER_NAMES = frozenset({
    ProviderName.OLLAMA,
    ProviderName.VLLM,
    ProviderName.LLAMA_CPP,
})
"""Provider enum members that are local servers."""


def _get_local_endpoint_url(provider_name: str) -> str:
    """Return the configured base URL for a local provider.

    Reads from ``os.environ`` (persisted to ``.env`` by the Settings
    page).  Raises :class:`ValueError` when no URL is configured so
    callers get a clear error instead of a silent wrong-port request.
    """
    from server.routes.settings import LOCAL_ENDPOINT_ENV_VARS

    env_var = LOCAL_ENDPOINT_ENV_VARS[provider_name]
    env_value = os.environ.get(env_var, "").strip()
    if not env_value:
        raise ValueError(
            f"No endpoint URL configured for local provider "
            f"{provider_name!r}. Set it in the API Keys page or add "
            f"{env_var!r} to the project-root .env file."
        )
    return env_value.rstrip("/")


class ModelListProxy:
    """Provider model-list proxy with a Redis-backed 10-minute cache.

    Attributes:
        redis_client (redis.Redis): Connection bound to the application
            Redis DB. Stores the serialised
            :class:`ProviderModelsResponse` as a string.
        http_client (httpx.AsyncClient): Long-lived async HTTP client
            owned by the FastAPI app. Reused across requests so
            connection pools warm up.
        key_prefix (str): Prefix applied to the cache key, matching
            :attr:`server.settings.ServerSettings.redis_key_prefix`.
        cache_ttl_seconds (int): TTL applied to every cache write.

    Methods:
        read: Return a :class:`ProviderModelsResponse` for the given
            provider, cache-first.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        http_client: httpx.AsyncClient,
        key_prefix: str,
        cache_ttl_seconds: int = MODEL_CACHE_TTL_SECONDS,
    ) -> None:
        """Store the injected dependencies and cache TTL.

        Args:
            redis_client (redis.Redis): Application Redis client.
            http_client (httpx.AsyncClient): Long-lived async HTTP
                client for upstream fetches.
            key_prefix (str): Prefix for cache keys.
            cache_ttl_seconds (int): TTL in seconds applied to every
                cache write. Defaults to
                :data:`MODEL_CACHE_TTL_SECONDS`.
        """
        self.redis_client = redis_client
        self.http_client = http_client
        self.key_prefix = key_prefix
        self.cache_ttl_seconds = cache_ttl_seconds

    async def read(self, provider: ProviderName) -> ProviderModelsResponse:
        """Return the cached model list or fetch it from the upstream.

        When Redis is reachable, results are cached for
        :attr:`cache_ttl_seconds`. When Redis is unavailable (e.g.
        Docker not running), the proxy degrades gracefully: it fetches
        directly from the upstream and returns the result without
        caching.

        Args:
            provider (ProviderName): Which provider to fetch.

        Returns:
            ProviderModelsResponse: The cached or newly-fetched list.

        Raises:
            ValueError: If the upstream responds with a non-2xx status
                code, if the response is not valid JSON, or if OpenAI
                is requested without an ``OPENAI_API_KEY`` in the
                environment.
        """
        cache_key = self._cache_key(provider)

        try:
            cached_payload = self.redis_client.get(cache_key)
            if cached_payload is not None:
                return ProviderModelsResponse.model_validate_json(cached_payload)
            redis_available = True
        except redis.ConnectionError:
            redis_available = False

        response_body = await self._fetch_upstream(provider)
        normalised_models = _normalise_models(provider, response_body)
        payload = ProviderModelsResponse(
            provider=provider,
            fetched_at=_now_iso(),
            models=normalised_models,
        )

        if redis_available:
            try:
                self.redis_client.set(
                    name=cache_key,
                    value=payload.model_dump_json(),
                    ex=self.cache_ttl_seconds,
                )
            except redis.ConnectionError:
                pass

        return payload

    def _cache_key(self, provider: ProviderName) -> str:
        """Return the Redis cache key for ``provider``.

        Args:
            provider (ProviderName): Which provider.

        Returns:
            str: ``f"{key_prefix}:models:{provider}"``.
        """
        return f"{self.key_prefix}:models:{provider.value}"

    async def _fetch_upstream(self, provider: ProviderName) -> Dict[str, Any]:
        """Fetch the upstream model list, raising on non-2xx responses.

        Args:
            provider (ProviderName): Which upstream to call.

        Returns:
            Dict[str, Any]: The decoded JSON response body.

        Raises:
            ValueError: If the upstream status is non-2xx, the body
                is not valid JSON, or (for OpenAI) the
                ``OPENAI_API_KEY`` environment variable is unset.
        """
        if provider is ProviderName.OPENROUTER:
            request_headers: Dict[str, str] = {}
            request_url = _OPENROUTER_MODELS_URL
        elif provider is ProviderName.OPENAI:
            api_key = os.environ.get(_OPENAI_API_KEY_ENV_VAR, "").strip()
            if not api_key:
                raise ValueError(
                    f"{_OPENAI_API_KEY_ENV_VAR} is not set; cannot fetch "
                    "the OpenAI model list."
                )
            request_headers = {"Authorization": f"Bearer {api_key}"}
            request_url = _OPENAI_MODELS_URL
        elif provider is ProviderName.CLAUDE:
            api_key = os.environ.get(_ANTHROPIC_API_KEY_ENV_VAR, "").strip()
            if not api_key:
                raise ValueError(
                    f"{_ANTHROPIC_API_KEY_ENV_VAR} is not set; cannot fetch "
                    "the Anthropic model list."
                )
            request_headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            }
            request_url = _ANTHROPIC_MODELS_URL
        elif provider is ProviderName.GOOGLE:
            api_key = os.environ.get(_GOOGLE_API_KEY_ENV_VAR, "").strip()
            if not api_key:
                raise ValueError(
                    f"{_GOOGLE_API_KEY_ENV_VAR} is not set; cannot fetch "
                    "the Google model list."
                )
            request_headers = {}
            request_url = f"{_GOOGLE_MODELS_URL}?key={api_key}"
        elif provider in _LOCAL_PROVIDER_NAMES:
            local_base = _get_local_endpoint_url(provider.value)
            request_headers = {"Authorization": "Bearer dummy"}
            request_url = f"{local_base}/models"
        else:  # pragma: no cover - exhaustiveness guard
            raise ValueError(f"Unknown provider: {provider}")

        try:
            response = await self.http_client.get(
                request_url, headers=request_headers, timeout=15.0
            )
        except httpx.HTTPError as exc:
            raise ValueError(
                f"Failed to fetch {provider.value} model list: {exc}"
            ) from exc

        if response.status_code >= 400:
            raise ValueError(
                f"{provider.value} model list returned HTTP "
                f"{response.status_code}: {response.text[:200]}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise ValueError(
                f"{provider.value} model list was not valid JSON: {exc}"
            ) from exc


def _normalise_models(
    provider: ProviderName, response_body: Dict[str, Any]
) -> List[ProviderModel]:
    """Project the upstream JSON into :class:`ProviderModel` entries.

    Args:
        provider (ProviderName): Which provider the body came from.
        response_body (Dict[str, Any]): Decoded upstream JSON.

    Returns:
        List[ProviderModel]: Normalised model entries sorted by
        :attr:`ProviderModel.id` so the GUI renders deterministically.
    """
    if provider is ProviderName.GOOGLE:
        return _normalise_google_models(response_body)

    raw_entries = response_body.get("data")
    if not isinstance(raw_entries, list):
        return []

    normalised: List[ProviderModel] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            continue
        model_id = str(raw_entry.get("id", "")).strip()
        if not model_id:
            continue
        if provider is ProviderName.OPENROUTER:
            display_label = str(raw_entry.get("name", model_id)).strip() or model_id
            description_value: object = raw_entry.get("description")
            description_text = (
                str(description_value).strip()
                if isinstance(description_value, str)
                else None
            )
            raw_context_length = raw_entry.get("context_length")
            context_length_int = (
                int(raw_context_length)
                if isinstance(raw_context_length, (int, float))
                else None
            )
        elif provider is ProviderName.CLAUDE:
            display_label = str(raw_entry.get("display_name", model_id)).strip() or model_id
            description_text = None
            raw_context_length = raw_entry.get("context_window")
            context_length_int = (
                int(raw_context_length)
                if isinstance(raw_context_length, (int, float))
                else None
            )
        else:
            display_label = model_id
            description_text = None
            context_length_int = None
        normalised.append(
            ProviderModel(
                id=model_id,
                label=display_label,
                description=description_text,
                context_length=context_length_int,
            )
        )
    normalised.sort(key=lambda entry: entry.id)
    return normalised


def _normalise_google_models(response_body: Dict[str, Any]) -> List[ProviderModel]:
    """Normalise Google's model list response.

    Google returns ``{"models": [{"name": "models/gemini-pro", ...}]}``
    rather than the ``{"data": [...]}`` shape used by other providers.
    """
    raw_entries = response_body.get("models")
    if not isinstance(raw_entries, list):
        return []

    normalised: List[ProviderModel] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            continue
        raw_name = str(raw_entry.get("name", "")).strip()
        if not raw_name:
            continue
        model_id = raw_name.removeprefix("models/")
        display_label = str(raw_entry.get("displayName", model_id)).strip() or model_id
        description_value: object = raw_entry.get("description")
        description_text = (
            str(description_value).strip()
            if isinstance(description_value, str)
            else None
        )
        raw_context_length = raw_entry.get("inputTokenLimit")
        context_length_int = (
            int(raw_context_length)
            if isinstance(raw_context_length, (int, float))
            else None
        )
        normalised.append(
            ProviderModel(
                id=model_id,
                label=display_label,
                description=description_text,
                context_length=context_length_int,
            )
        )
    normalised.sort(key=lambda entry: entry.id)
    return normalised


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string.

    Returns:
        str: Current UTC timestamp with ``+00:00`` offset.
    """
    return datetime.now(tz=timezone.utc).isoformat()


__all__ = [
    "MODEL_CACHE_TTL_SECONDS",
    "ModelListProxy",
]
