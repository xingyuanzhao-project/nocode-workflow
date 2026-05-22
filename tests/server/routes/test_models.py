"""Route tests for ``/api/models/{provider}``.

Uses :mod:`respx` to intercept the proxy's upstream calls and
fakeredis as the cache (via the ``test_client`` fixture).
"""

from __future__ import annotations

import httpx
import pytest
import respx
from fastapi.testclient import TestClient


class TestProviderModelsRoute:
    def test_openrouter_happy_path(
        self,
        test_client: TestClient,
        openrouter_models_json,
    ) -> None:
        with respx.mock() as mock_router:
            mock_router.get("https://openrouter.ai/api/v1/models").mock(
                return_value=httpx.Response(200, json=openrouter_models_json)
            )
            response = test_client.get("/api/models/openrouter")
        assert response.status_code == 200
        body = response.json()
        assert body["provider"] == "openrouter"
        assert {m["id"] for m in body["models"]} >= {
            "meta-llama/llama-3.1-70b-instruct",
            "google/gemini-2.5-flash",
        }

    def test_unknown_provider_returns_422(self, test_client: TestClient) -> None:
        response = test_client.get("/api/models/not_a_provider")
        assert response.status_code == 422

    def test_openai_without_api_key_returns_400(
        self, test_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        response = test_client.get("/api/models/openai")
        assert response.status_code == 400
        assert "OPENAI_API_KEY" in response.text

    def test_openrouter_cache_hit_on_second_call(
        self,
        test_client: TestClient,
        fake_redis_client,
        openrouter_models_json,
    ) -> None:
        # Clear any cache key a previous test populated so this test
        # can assert that the *first* call goes upstream.
        for cached_key in fake_redis_client.keys("*:models:openrouter"):
            fake_redis_client.delete(cached_key)
        with respx.mock(assert_all_called=False) as mock_router:
            route = mock_router.get("https://openrouter.ai/api/v1/models").mock(
                return_value=httpx.Response(200, json=openrouter_models_json)
            )
            first_response = test_client.get("/api/models/openrouter")
            second_response = test_client.get("/api/models/openrouter")
        assert first_response.status_code == 200
        assert second_response.status_code == 200
        # Upstream is hit exactly once; second request serves from cache.
        assert route.call_count == 1
