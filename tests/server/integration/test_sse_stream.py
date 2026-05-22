"""Integration test for the live SSE log stream.

Submits a short run and subscribes to
``/api/flow/runs/{run_id}/logs/stream`` via :mod:`httpx` streaming
mode. Asserts at least one ``event: log`` frame arrives and that a
terminal ``event: status`` frame follows.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import List

import httpx
import pytest

from ._docker_probe import require_running_stack
from ._integration_client import (
    DEFAULT_BASE_URL,
    build_single_summary_flow,
    submit_adhoc_run,
    upload_csv,
)


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def _stack_up() -> None:
    require_running_stack()


class TestSseStream:
    def test_log_events_then_status_event(self, project_root: Path) -> None:
        upload_response = upload_csv(project_root / "data" / "df_text_by_report.csv")
        flow = build_single_summary_flow(upload_response["stored_path"])
        run_id = submit_adhoc_run(flow)

        log_event_count = 0
        terminal_status_seen: str | None = None
        started = time.monotonic()
        with httpx.Client(base_url=DEFAULT_BASE_URL, timeout=None) as client:
            with client.stream(
                "GET", f"/api/flow/runs/{run_id}/logs/stream"
            ) as response:
                response.raise_for_status()
                current_event: str | None = None
                for raw_line in response.iter_lines():
                    if raw_line.startswith("event:"):
                        current_event = raw_line[len("event:") :].strip()
                    elif raw_line.startswith("data:") and current_event == "log":
                        log_event_count += 1
                    elif raw_line.startswith("data:") and current_event == "status":
                        terminal_status_seen = raw_line[len("data:") :].strip()
                        break
                    if time.monotonic() - started > 900:
                        pytest.fail("SSE stream did not complete within 15 minutes")

        assert log_event_count >= 1, "No log events arrived on the SSE channel"
        assert terminal_status_seen == "succeeded"
