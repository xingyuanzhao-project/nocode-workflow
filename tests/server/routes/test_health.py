"""Route tests for ``GET /api/health``."""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestHealthEndpoint:
    def test_healthy_when_redis_and_worker_ok(
        self, test_client: TestClient, monkeypatch
    ) -> None:
        from server.routes import health as health_module

        monkeypatch.setattr(health_module, "_ping_redis", lambda: True)
        monkeypatch.setattr(health_module, "_ping_worker", lambda _celery_app: True)
        response = test_client.get("/api/health")
        assert response.status_code == 200
        body = response.json()
        assert body == {"status": "ok", "redis_ok": True, "worker_ok": True}

    def test_degraded_when_redis_down(
        self, test_client: TestClient, monkeypatch
    ) -> None:
        from server.routes import health as health_module

        monkeypatch.setattr(health_module, "_ping_redis", lambda: False)
        monkeypatch.setattr(health_module, "_ping_worker", lambda _celery_app: True)
        body = test_client.get("/api/health").json()
        assert body["status"] == "degraded"
        assert body["redis_ok"] is False
        assert body["worker_ok"] is True

    def test_degraded_when_worker_down(
        self, test_client: TestClient, monkeypatch
    ) -> None:
        from server.routes import health as health_module

        monkeypatch.setattr(health_module, "_ping_redis", lambda: True)
        monkeypatch.setattr(health_module, "_ping_worker", lambda _celery_app: False)
        body = test_client.get("/api/health").json()
        assert body["status"] == "degraded"
        assert body["worker_ok"] is False
