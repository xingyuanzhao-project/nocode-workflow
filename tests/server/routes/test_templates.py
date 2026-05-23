"""Route tests for ``/api/flow/templates``."""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestTemplatesListRoute:
    def test_list_returns_shipped_templates(self, test_client: TestClient) -> None:
        response = test_client.get("/api/flow/templates")
        assert response.status_code == 200
        ids = {item["id"] for item in response.json()}
        assert {
            "label_extraction_summary",
            "flat_summary_classification",
            "full_pipeline",
        } <= ids


class TestTemplateDetailRoute:
    def test_get_known_template_returns_flow_body(
        self, test_client: TestClient
    ) -> None:
        response = test_client.get("/api/flow/templates/full_pipeline")
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == "full_pipeline"
        assert "nodes" in body["flow"]

    def test_get_unknown_template_returns_404(
        self, test_client: TestClient
    ) -> None:
        response = test_client.get("/api/flow/templates/nope")
        assert response.status_code == 404

    def test_unknown_template_does_not_match_saved_flow_route(
        self, test_client: TestClient
    ) -> None:
        # Regression guard: the templates router must be registered
        # before the flow CRUD router so ``/api/flow/templates/...``
        # doesn't fall through to ``GET /api/flow/{flow_id}``.
        response = test_client.get("/api/flow/templates")
        # If fallthrough happened the response would be a
        # FlowGetResponse object, not a list.
        assert isinstance(response.json(), list)
