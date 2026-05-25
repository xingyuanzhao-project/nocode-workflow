"""Route tests for ``/api/codebook``."""

from __future__ import annotations

from fastapi.testclient import TestClient


_CODEBOOK_BODY = {
    "desenlace": {
        "definition": "Outcome",
        "options": ["muerte", "herido", "ileso"],
        "context_definition": "Pick the outcome.",
    }
}


class TestCodebookRoutes:
    def test_crud_round_trip(self, test_client: TestClient) -> None:
        assert test_client.get("/api/codebook").json() == []

        create_response = test_client.post(
            "/api/codebook",
            json={"name": "Human Rights", "codebook": _CODEBOOK_BODY},
        )
        assert create_response.status_code == 201
        codebook_id = create_response.json()["id"]

        listed = test_client.get("/api/codebook").json()
        assert len(listed) == 1
        assert listed[0]["id"] == codebook_id

        fetched = test_client.get(f"/api/codebook/{codebook_id}").json()
        assert fetched["name"] == "Human Rights"
        assert fetched["codebook"]["desenlace"] == _CODEBOOK_BODY["desenlace"]

        update_response = test_client.put(
            f"/api/codebook/{codebook_id}",
            json={"name": "Human Rights", "codebook": _CODEBOOK_BODY},
        )
        assert update_response.status_code == 200

        delete_response = test_client.delete(f"/api/codebook/{codebook_id}")
        assert delete_response.status_code == 204
        assert test_client.get(f"/api/codebook/{codebook_id}").status_code == 404

    def test_get_unknown_returns_404(self, test_client: TestClient) -> None:
        assert test_client.get("/api/codebook/does_not_exist").status_code == 404

    def test_delete_unknown_returns_404(self, test_client: TestClient) -> None:
        assert test_client.delete("/api/codebook/does_not_exist").status_code == 404
