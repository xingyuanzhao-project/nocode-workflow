"""Unit tests for :class:`server.services.run_registry.RunRegistry`.

Pins every state transition against fakeredis and asserts the
terminal-TTL behaviour that the caller relies on.
"""

from __future__ import annotations

import json

import pytest

from server.schemas.run import RunStatus
from server.services.run_registry import RunRegistry


@pytest.fixture
def run_registry(
    server_paths,
    fake_redis_client,
) -> RunRegistry:
    """Build a :class:`RunRegistry` bound to fakeredis.

    Returns:
        RunRegistry: Registry with a 60-second terminal TTL.
    """
    return RunRegistry(
        paths=server_paths,
        redis_client=fake_redis_client,
        key_prefix="agent_paper_test",
        terminal_ttl_seconds=60,
    )


class TestRunRegistryLifecycle:
    def test_create_sets_status_queued(
        self, run_registry: RunRegistry, fake_redis_client
    ) -> None:
        run_registry.create("r1")
        hash_contents = fake_redis_client.hgetall("agent_paper_test:run:r1")
        assert hash_contents["status"] == RunStatus.QUEUED.value
        assert "started_at" not in hash_contents

    def test_mark_running_stamps_started_at(
        self, run_registry: RunRegistry, fake_redis_client
    ) -> None:
        run_registry.create("r1")
        run_registry.mark_running("r1")
        hash_contents = fake_redis_client.hgetall("agent_paper_test:run:r1")
        assert hash_contents["status"] == RunStatus.RUNNING.value
        assert hash_contents["started_at"]

    def test_mark_succeeded_applies_terminal_ttl(
        self, run_registry: RunRegistry, fake_redis_client
    ) -> None:
        run_registry.create("r1")
        run_registry.mark_succeeded("r1")
        ttl = fake_redis_client.ttl("agent_paper_test:run:r1")
        assert 0 < ttl <= 60
        hash_contents = fake_redis_client.hgetall("agent_paper_test:run:r1")
        assert hash_contents["status"] == RunStatus.SUCCEEDED.value
        assert hash_contents["finished_at"]

    def test_mark_failed_stores_error_verbatim(
        self, run_registry: RunRegistry, fake_redis_client
    ) -> None:
        # The RunRegistry itself does not truncate; truncation happens
        # in the signals module before the call reaches the registry.
        # The service faithfully persists whatever it is given.
        run_registry.create("r1")
        message = "short repr(exception) message"
        run_registry.mark_failed("r1", message)
        hash_contents = fake_redis_client.hgetall("agent_paper_test:run:r1")
        assert hash_contents["status"] == RunStatus.FAILED.value
        assert hash_contents["error"] == message

    def test_create_resets_after_terminal(
        self, run_registry: RunRegistry, fake_redis_client
    ) -> None:
        run_registry.create("r1")
        run_registry.mark_failed("r1", "oops")
        run_registry.create("r1")  # Resume path.
        hash_contents = fake_redis_client.hgetall("agent_paper_test:run:r1")
        assert hash_contents["status"] == RunStatus.QUEUED.value
        assert "error" not in hash_contents
        # TTL cleared so the fresh entry is not auto-evicted.
        assert fake_redis_client.ttl("agent_paper_test:run:r1") == -1


class TestRunRegistryGet:
    def test_get_unknown_raises(self, run_registry: RunRegistry) -> None:
        with pytest.raises(FileNotFoundError):
            run_registry.get("does_not_exist")

    def test_get_enriches_with_checkpoint_count(
        self, run_registry: RunRegistry, server_paths
    ) -> None:
        run_registry.create("r1")
        run_directory = server_paths.runs_dir / "r1"
        checkpoint_dir = run_directory / ".checkpoint"
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        (checkpoint_dir / "completed_entities.json").write_text(
            json.dumps({"completed": ["alpha", "bravo", "charlie"]}),
            encoding="utf-8",
        )
        status = run_registry.get("r1")
        assert status.completed_entity_count == 3

    def test_get_handles_missing_checkpoint_gracefully(
        self, run_registry: RunRegistry
    ) -> None:
        run_registry.create("r1")
        status = run_registry.get("r1")
        assert status.completed_entity_count == 0
