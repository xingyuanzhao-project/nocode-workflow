"""Route tests for ``/api/flow/workflows``."""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestWorkflowsListRoute:
    def test_list_returns_shipped_workflows(self, test_client: TestClient) -> None:
        response = test_client.get("/api/flow/workflows")
        assert response.status_code == 200
        ids = {item["id"] for item in response.json()}
        assert {
            "label_extraction_summary",
            "flat_summary_classification",
            "full_pipeline",
        } <= ids


class TestWorkflowDetailRoute:
    def test_get_known_workflow_returns_flow_body(
        self, test_client: TestClient
    ) -> None:
        response = test_client.get("/api/flow/workflows/full_pipeline")
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == "full_pipeline"
        assert "nodes" in body["flow"]

    def test_get_unknown_workflow_returns_404(
        self, test_client: TestClient
    ) -> None:
        response = test_client.get("/api/flow/workflows/nope")
        assert response.status_code == 404

    def test_unknown_workflow_does_not_match_saved_flow_route(
        self, test_client: TestClient
    ) -> None:
        response = test_client.get("/api/flow/workflows")
        assert isinstance(response.json(), list)
