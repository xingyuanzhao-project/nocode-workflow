"""Route tests for ``/api/taxonomy``."""

from __future__ import annotations

from fastapi.testclient import TestClient


_TAXONOMY_BODY = {
    "desenlace": {
        "definition": "Outcome",
        "options": ["muerte", "herido", "ileso"],
        "context_definition": "Pick the outcome.",
    }
}


class TestTaxonomyRoutes:
    def test_crud_round_trip(self, test_client: TestClient) -> None:
        assert test_client.get("/api/taxonomy").json() == []

        create_response = test_client.post(
            "/api/taxonomy",
            json={"name": "Human Rights", "taxonomy": _TAXONOMY_BODY},
        )
        assert create_response.status_code == 201
        taxonomy_id = create_response.json()["id"]

        listed = test_client.get("/api/taxonomy").json()
        assert len(listed) == 1
        assert listed[0]["id"] == taxonomy_id

        fetched = test_client.get(f"/api/taxonomy/{taxonomy_id}").json()
        assert fetched["name"] == "Human Rights"
        assert fetched["taxonomy"]["desenlace"] == _TAXONOMY_BODY["desenlace"]

        update_response = test_client.put(
            f"/api/taxonomy/{taxonomy_id}",
            json={"name": "Human Rights", "taxonomy": _TAXONOMY_BODY},
        )
        assert update_response.status_code == 200

        delete_response = test_client.delete(f"/api/taxonomy/{taxonomy_id}")
        assert delete_response.status_code == 204
        assert test_client.get(f"/api/taxonomy/{taxonomy_id}").status_code == 404

    def test_get_unknown_returns_404(self, test_client: TestClient) -> None:
        assert test_client.get("/api/taxonomy/does_not_exist").status_code == 404

    def test_delete_unknown_returns_404(self, test_client: TestClient) -> None:
        assert test_client.delete("/api/taxonomy/does_not_exist").status_code == 404
