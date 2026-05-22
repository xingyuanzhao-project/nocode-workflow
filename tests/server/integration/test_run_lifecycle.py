"""Integration tests for the run lifecycle against the live stack."""

from __future__ import annotations

from pathlib import Path

import pytest

from ._docker_probe import require_running_stack
from ._integration_client import (
    build_conversation_summary_flow,
    build_single_summary_flow,
    poll_run_until_terminal,
    submit_adhoc_run,
    upload_csv,
)


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def _stack_up() -> None:
    """Skip the module if the docker compose stack is not running."""
    require_running_stack()


@pytest.fixture(scope="module")
def uploaded_csv_stored_path(project_root: Path) -> str:
    """Upload ``data/df_text_by_report.csv`` once per module and return stored_path."""
    upload_response = upload_csv(project_root / "data" / "df_text_by_report.csv")
    return upload_response["stored_path"]


class TestConversationSummaryRun:
    def test_run_reaches_succeeded(self, uploaded_csv_stored_path: str) -> None:
        flow = build_conversation_summary_flow(uploaded_csv_stored_path)
        run_id = submit_adhoc_run(flow)
        final = poll_run_until_terminal(run_id)
        assert final["status"] == "succeeded"
        assert final["completed_entity_count"] >= 1


class TestSingleSummaryRowRun:
    def test_row_unit_flow_succeeds(self, uploaded_csv_stored_path: str) -> None:
        flow = build_single_summary_flow(uploaded_csv_stored_path)
        run_id = submit_adhoc_run(flow)
        final = poll_run_until_terminal(run_id, timeout_seconds=600.0)
        assert final["status"] == "succeeded"
