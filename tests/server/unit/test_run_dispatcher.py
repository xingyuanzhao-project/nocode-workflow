"""Unit tests for :class:`server.services.run_dispatcher.RunDispatcher`.

Uses the ``recorded_celery_app`` fixture so we can assert which task
name and args were enqueued without actually running the worker.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from server.services.flow_validation import FlowValidator
from server.services.run_dispatcher import FLOW_TASK_NAME, RunDispatcher
from server.services.run_registry import RunRegistry


@pytest.fixture
def run_dispatcher(
    server_paths,
    fake_redis_client,
    recorded_celery_app,
    flow_validator: FlowValidator,
) -> RunDispatcher:
    """Build a :class:`RunDispatcher` with a recorded Celery stand-in."""
    registry = RunRegistry(
        paths=server_paths,
        redis_client=fake_redis_client,
        key_prefix="agent_paper_test",
        terminal_ttl_seconds=60,
    )
    return RunDispatcher(
        paths=server_paths,
        registry=registry,
        celery_app=recorded_celery_app,
        validator=flow_validator,
    )


class TestRunDispatcherSubmit:
    def test_submit_writes_flow_yaml_and_enqueues_task(
        self,
        run_dispatcher: RunDispatcher,
        valid_flow_body: dict,
        recorded_celery_app,
        server_paths,
    ) -> None:
        response = run_dispatcher.submit(valid_flow_body)
        assert response.run_id
        run_directory = server_paths.runs_dir / response.run_id
        flow_yaml_path = run_directory / "flow.yml"
        assert flow_yaml_path.is_file()
        assert recorded_celery_app.calls == [
            {
                "name": FLOW_TASK_NAME,
                "args": [response.run_id],
                "kwargs": {},
            }
        ]

    def test_submit_rewrites_every_output_path(
        self,
        run_dispatcher: RunDispatcher,
        valid_flow_body: dict,
        server_paths,
    ) -> None:
        flow_copy = copy.deepcopy(valid_flow_body)
        for node in flow_copy.get("nodes", []):
            if node.get("type") in ("csv_output", "json_output"):
                node["config"] = {
                    "output_path": "wherever/summary.csv",
                    "artifact_paths": [
                        "wherever/results.csv",
                        "wherever/states.csv",
                        "wherever/spans.csv",
                    ],
                    "extend": False,
                }
        response = run_dispatcher.submit(flow_copy)
        written_yaml = (
            server_paths.runs_dir / response.run_id / "flow.yml"
        ).read_text(encoding="utf-8")
        rewritten_flow = yaml.safe_load(written_yaml)["flow"]
        expected_prefix = f"{server_paths.runs_dir_relative_posix}/{response.run_id}/"
        for node in rewritten_flow.get("nodes", []):
            if node.get("type") in ("csv_output", "json_output"):
                node_config = node.get("config", {})
                assert node_config["output_path"] == f"{expected_prefix}summary.csv"
                artifacts = node_config.get("artifact_paths", [])
                assert artifacts[0] == f"{expected_prefix}results.csv"
                assert artifacts[1] == f"{expected_prefix}states.csv"
                assert artifacts[2] == f"{expected_prefix}spans.csv"
        logging_block = rewritten_flow.get("settings", {}).get("logging", {})
        assert logging_block["file"].endswith(
            f"/{response.run_id}/worker.log"
        )

    def test_submit_mints_distinct_run_ids(
        self, run_dispatcher: RunDispatcher, valid_flow_body: dict
    ) -> None:
        first = run_dispatcher.submit(valid_flow_body)
        second = run_dispatcher.submit(valid_flow_body)
        assert first.run_id != second.run_id

    def test_invalid_flow_rejected_before_enqueue(
        self,
        run_dispatcher: RunDispatcher,
        recorded_celery_app,
    ) -> None:
        with pytest.raises(ValueError):
            run_dispatcher.submit({"definitely": "not a flow"})
        assert recorded_celery_app.calls == []


class TestRunDispatcherResume:
    def test_resume_reuses_existing_yaml(
        self,
        run_dispatcher: RunDispatcher,
        valid_flow_body: dict,
        recorded_celery_app,
        server_paths,
    ) -> None:
        first = run_dispatcher.submit(valid_flow_body)
        first_yaml_text = (
            server_paths.runs_dir / first.run_id / "flow.yml"
        ).read_text(encoding="utf-8")
        recorded_celery_app.calls.clear()

        resume_response = run_dispatcher.resume(first.run_id)
        assert resume_response.run_id == first.run_id
        # YAML on disk must not have changed.
        second_yaml_text = (
            server_paths.runs_dir / first.run_id / "flow.yml"
        ).read_text(encoding="utf-8")
        assert first_yaml_text == second_yaml_text
        # Task re-enqueued under the same run id.
        assert recorded_celery_app.calls == [
            {
                "name": FLOW_TASK_NAME,
                "args": [first.run_id],
                "kwargs": {},
            }
        ]

    def test_resume_unknown_run_raises(
        self, run_dispatcher: RunDispatcher
    ) -> None:
        with pytest.raises(FileNotFoundError, match="cannot resume"):
            run_dispatcher.resume("never_submitted")
