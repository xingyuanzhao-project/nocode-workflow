"""Route tests for ``GET /api/schema/node-types`` and ``POST /api/schema/validate``."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient


class TestListNodeTypes:
    def test_returns_registered_entries(self, test_client: TestClient) -> None:
        response = test_client.get("/api/schema/node-types")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body.get("entries"), list)
        entry_ids = {entry["id"] for entry in body["entries"]}
        for required in [
            "csv_input",
            "llm_call",
            "codebook",
            "single_summary",
            "classification",
            "label_extraction",
            "label_summary",
        ]:
            assert required in entry_ids


class TestValidateEndpoint:
    def test_valid_flow_returns_true(
        self, test_client: TestClient, valid_flow_body: dict
    ) -> None:
        response = test_client.post(
            "/api/schema/validate", json={"flow": valid_flow_body}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["valid"] is True
        assert body["errors"] == []

    def test_invalid_flow_returns_errors(
        self, test_client: TestClient, fixtures_dir: Path
    ) -> None:
        with (
            fixtures_dir / "invalid_flow_missing_steps.yml"
        ).open("r", encoding="utf-8") as file_handle:
            flow_body = yaml.safe_load(file_handle)["flow"]
        response = test_client.post(
            "/api/schema/validate", json={"flow": flow_body}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["valid"] is False
        assert body["errors"]

    def test_missing_flow_key_returns_422(self, test_client: TestClient) -> None:
        response = test_client.post("/api/schema/validate", json={})
        assert response.status_code == 422
