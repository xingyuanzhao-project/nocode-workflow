"""Unit tests for :class:`server.services.model_list_proxy.ModelListProxy`.

Uses :mod:`respx` to intercept the upstream HTTP calls and
:mod:`fakeredis` as the cache.
"""

from __future__ import annotations

import json
from typing import Any, Dict

import httpx
import pytest
import respx

from server.schemas.models import ProviderName
from server.services.model_list_proxy import (
    MODEL_CACHE_TTL_SECONDS,
    ModelListProxy,
)


@pytest.fixture
async def async_http_client() -> httpx.AsyncClient:
    """Yield a fresh :class:`httpx.AsyncClient` closed at teardown."""
    async with httpx.AsyncClient() as client:
        yield client


@pytest.fixture
def proxy(
    fake_redis_client,
    async_http_client,
) -> ModelListProxy:
    """Build a :class:`ModelListProxy` with fakeredis + respx-friendly httpx."""
    return ModelListProxy(
        redis_client=fake_redis_client,
        http_client=async_http_client,
        key_prefix="academic_pipeline_test",
        cache_ttl_seconds=MODEL_CACHE_TTL_SECONDS,
    )


class TestModelListProxyCacheMissThenHit:
    @pytest.mark.asyncio
    async def test_openrouter_cache_miss_calls_upstream(
        self,
        proxy: ModelListProxy,
        fake_redis_client,
        openrouter_models_json: Dict[str, Any],
    ) -> None:
        with respx.mock(assert_all_called=True) as mock_router:
            route = mock_router.get("https://openrouter.ai/api/v1/models").mock(
                return_value=httpx.Response(200, json=openrouter_models_json)
            )
            response = await proxy.read(ProviderName.OPENROUTER)
        assert route.called
        assert [model.id for model in response.models] == [
            "google/gemini-2.5-flash",
            "meta-llama/llama-3.1-70b-instruct",
            "openai/gpt-4o-mini",
        ]
        cached_payload = fake_redis_client.get("academic_pipeline_test:models:openrouter")
        assert cached_payload is not None
        # The stored value is the serialised DTO, not the raw upstream JSON.
        assert "fetched_at" in json.loads(cached_payload)

    @pytest.mark.asyncio
    async def test_openrouter_cache_hit_skips_upstream(
        self,
        proxy: ModelListProxy,
        fake_redis_client,
        openrouter_models_json: Dict[str, Any],
    ) -> None:
        # Prime the cache with one upstream call.
        with respx.mock() as mock_router:
            mock_router.get("https://openrouter.ai/api/v1/models").mock(
                return_value=httpx.Response(200, json=openrouter_models_json)
            )
            await proxy.read(ProviderName.OPENROUTER)
        # Second call must not hit the network.
        with respx.mock(assert_all_called=False) as mock_router:
            route = mock_router.get("https://openrouter.ai/api/v1/models")
            response = await proxy.read(ProviderName.OPENROUTER)
        assert not route.called
        assert response.models


class TestModelListProxyUpstreamFailures:
    @pytest.mark.asyncio
    async def test_openai_without_api_key_env_raises_value_error(
        self, proxy: ModelListProxy, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            await proxy.read(ProviderName.OPENAI)

    @pytest.mark.asyncio
    async def test_openrouter_upstream_500_raises(
        self, proxy: ModelListProxy
    ) -> None:
        with respx.mock() as mock_router:
            mock_router.get("https://openrouter.ai/api/v1/models").mock(
                return_value=httpx.Response(500, text="boom")
            )
            with pytest.raises(ValueError, match="openrouter model list returned HTTP 500"):
                await proxy.read(ProviderName.OPENROUTER)

    @pytest.mark.asyncio
    async def test_openrouter_invalid_json_raises(
        self, proxy: ModelListProxy
    ) -> None:
        with respx.mock() as mock_router:
            mock_router.get("https://openrouter.ai/api/v1/models").mock(
                return_value=httpx.Response(200, text="not json")
            )
            with pytest.raises(ValueError, match="not valid JSON"):
                await proxy.read(ProviderName.OPENROUTER)

    @pytest.mark.asyncio
    async def test_openai_happy_path_with_api_key(
        self,
        proxy: ModelListProxy,
        monkeypatch: pytest.MonkeyPatch,
        openai_models_json: Dict[str, Any],
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-abcd")
        with respx.mock() as mock_router:
            mock_router.get("https://api.openai.com/v1/models").mock(
                return_value=httpx.Response(200, json=openai_models_json)
            )
            response = await proxy.read(ProviderName.OPENAI)
        assert {model.id for model in response.models} == {
            "gpt-4o-mini",
            "gpt-4o",
            "gpt-3.5-turbo",
        }
