"""Integration tests for the results preview and artifact download endpoints."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from ._docker_probe import require_running_stack
from ._integration_client import (
    DEFAULT_BASE_URL,
    build_single_summary_flow,
    poll_run_until_terminal,
    request_json,
    submit_adhoc_run,
    upload_csv,
)


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def _stack_up() -> None:
    require_running_stack()


@pytest.fixture(scope="module")
def succeeded_run_id(project_root: Path) -> str:
    upload_response = upload_csv(project_root / "data" / "df_text_by_report.csv")
    flow = build_single_summary_flow(upload_response["stored_path"])
    run_id = submit_adhoc_run(flow)
    final = poll_run_until_terminal(run_id)
    assert final["status"] == "succeeded"
    return run_id


class TestPreviewEndpointAgainstLiveRun:
    def test_preview_shows_at_least_one_row(self, succeeded_run_id: str) -> None:
        preview = request_json(
            "GET",
            f"/api/flow/runs/{succeeded_run_id}/preview?artifact=summary&limit=10",
        )
        assert preview["artifact_name"] == "summary"
        assert preview["total_row_count"] >= 1
        assert len(preview["preview_rows"]) >= 1

    def test_total_row_count_is_greater_or_equal_to_preview(
        self, succeeded_run_id: str
    ) -> None:
        preview = request_json(
            "GET",
            f"/api/flow/runs/{succeeded_run_id}/preview?artifact=summary&limit=5",
        )
        assert preview["total_row_count"] >= len(preview["preview_rows"])


class TestArtifactDownloadAgainstLiveRun:
    def test_summary_artifact_downloads_as_csv(self, succeeded_run_id: str) -> None:
        with httpx.Client(base_url=DEFAULT_BASE_URL, timeout=30.0) as client:
            response = client.get(
                f"/api/flow/runs/{succeeded_run_id}/artifacts/summary"
            )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert b"," in response.content
