"""Route tests for ``GET /api/prompts``."""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestPromptsRoute:
    def test_returns_prompts_path_and_keys(self, test_client: TestClient) -> None:
        response = test_client.get("/api/prompts")
        assert response.status_code == 200
        body = response.json()
        assert body["path"] == "config/prompts.json"
        assert "summary" in body["prompts"]
        assert isinstance(body["prompts"]["summary"]["instructions"], list)
