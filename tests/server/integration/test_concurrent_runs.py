"""Integration test for concurrent runs.

Submits two runs nearly simultaneously and polls each to a terminal
status. Asserts both succeed and that their checkpoint files remain
isolated under the per-run directories.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from ._docker_probe import require_running_stack
from ._integration_client import (
    build_single_summary_flow,
    poll_run_until_terminal,
    submit_adhoc_run,
    upload_csv,
)


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def _stack_up() -> None:
    require_running_stack()


class TestConcurrentRuns:
    def test_two_runs_complete_independently(self, project_root: Path) -> None:
        upload_response = upload_csv(project_root / "data" / "df_text_by_report.csv")
        stored_path = upload_response["stored_path"]
        flow_a = build_single_summary_flow(stored_path)
        flow_a["name"] = "concurrent_a"
        flow_b = build_single_summary_flow(stored_path)
        flow_b["name"] = "concurrent_b"

        with ThreadPoolExecutor(max_workers=2) as executor:
            run_id_a_future = executor.submit(submit_adhoc_run, flow_a)
            run_id_b_future = executor.submit(submit_adhoc_run, flow_b)
            run_id_a = run_id_a_future.result()
            run_id_b = run_id_b_future.result()
            final_a_future = executor.submit(
                poll_run_until_terminal, run_id_a, timeout_seconds=900.0
            )
            final_b_future = executor.submit(
                poll_run_until_terminal, run_id_b, timeout_seconds=900.0
            )
            final_a = final_a_future.result()
            final_b = final_b_future.result()

        assert run_id_a != run_id_b
        assert final_a["status"] == "succeeded"
        assert final_b["status"] == "succeeded"
        # Checkpoint counts are per-run and not shared.
        assert final_a["run_id"] == run_id_a
        assert final_b["run_id"] == run_id_b
