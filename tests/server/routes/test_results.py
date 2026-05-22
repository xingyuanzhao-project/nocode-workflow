"""Route tests for the preview + artifact download endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


class TestPreviewEndpoint:
    def test_preview_default_artifact(
        self, test_client: TestClient, summary_csv_fixture_path: Path
    ) -> None:
        response = test_client.get(
            "/api/flow/runs/preview_fixture_run/preview?limit=5"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["artifact_name"] == "summary"
        assert len(body["preview_rows"]) == 5
        assert body["total_row_count"] == 30

    def test_preview_rejects_negative_limit(
        self, test_client: TestClient, summary_csv_fixture_path: Path
    ) -> None:
        response = test_client.get(
            "/api/flow/runs/preview_fixture_run/preview?limit=-1"
        )
        assert response.status_code == 422

    def test_preview_clamps_past_maximum(
        self, test_client: TestClient, summary_csv_fixture_path: Path
    ) -> None:
        response = test_client.get(
            "/api/flow/runs/preview_fixture_run/preview?limit=10000"
        )
        assert response.status_code == 422

    def test_preview_rejects_unknown_artifact(
        self, test_client: TestClient, summary_csv_fixture_path: Path
    ) -> None:
        response = test_client.get(
            "/api/flow/runs/preview_fixture_run/preview?artifact=bogus"
        )
        assert response.status_code == 422

    def test_preview_missing_file_returns_404(
        self, test_client: TestClient
    ) -> None:
        response = test_client.get(
            "/api/flow/runs/does_not_exist/preview?artifact=summary"
        )
        assert response.status_code == 404


class TestArtifactDownloadEndpoint:
    def test_download_summary_returns_csv(
        self, test_client: TestClient, summary_csv_fixture_path: Path
    ) -> None:
        response = test_client.get(
            "/api/flow/runs/preview_fixture_run/artifacts/summary"
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert "attachment" in response.headers["content-disposition"]
        assert "preview_fixture_run_summary.csv" in response.headers[
            "content-disposition"
        ]
        assert b"entity_id,summary" in response.content

    def test_download_missing_artifact_returns_404(
        self, test_client: TestClient
    ) -> None:
        response = test_client.get(
            "/api/flow/runs/nothing/artifacts/summary"
        )
        assert response.status_code == 404

    def test_download_rejects_unknown_artifact_name(
        self, test_client: TestClient
    ) -> None:
        response = test_client.get(
            "/api/flow/runs/anything/artifacts/bogus_name"
        )
        assert response.status_code == 422
