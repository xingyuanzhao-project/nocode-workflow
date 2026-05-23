"""Unit tests for :class:`server.services.log_stream.LogStreamService`.

Uses :mod:`fakeredis.aioredis.FakeRedis` + a shared in-memory server
so both the publisher (our test body) and the subscriber (the service
under test) see the same Redis.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Dict, List

import fakeredis
import pytest
from fakeredis import aioredis as fake_aioredis

from server.schemas.run import RunStatus, RunStatusDTO
from server.services.log_stream import LogStreamService


class _StaticRegistry:
    """Minimal stand-in for :class:`RunRegistry` used by the stream tests.

    Attributes:
        status (RunStatus): Status returned by :meth:`get`.
        flip_after (int): Number of ``get`` calls after which the
            registry transitions to ``succeeded``. Used to simulate a
            run that finishes after a few log lines arrived.
    """

    def __init__(self, flip_after: int = 2) -> None:
        self.status: RunStatus = RunStatus.RUNNING
        self.flip_after: int = flip_after
        self._calls: int = 0

    def get(self, run_id: str) -> RunStatusDTO:
        self._calls += 1
        if self._calls > self.flip_after:
            self.status = RunStatus.SUCCEEDED
        return RunStatusDTO(run_id=run_id, status=self.status)


@pytest.fixture
def shared_fake_server() -> fakeredis.FakeServer:
    """Return a fakeredis server shared by publisher and subscriber."""
    return fakeredis.FakeServer()


@pytest.fixture
def log_stream_service(
    shared_fake_server: fakeredis.FakeServer,
    monkeypatch: pytest.MonkeyPatch,
) -> LogStreamService:
    """Redirect ``aioredis.from_url`` to fakeredis and return the service."""

    def _fake_from_url(
        _url: str, *, decode_responses: bool = True
    ) -> fake_aioredis.FakeRedis:
        return fake_aioredis.FakeRedis(
            server=shared_fake_server, decode_responses=decode_responses
        )

    from server.services import log_stream as log_stream_module

    monkeypatch.setattr(log_stream_module.aioredis, "from_url", _fake_from_url)
    registry = _StaticRegistry(flip_after=2)
    return LogStreamService(
        async_redis_url="redis://unused/0",
        key_prefix="academic_pipeline_test",
        registry=registry,
    )


@pytest.mark.asyncio
async def test_stream_yields_log_then_terminal_status(
    log_stream_service: LogStreamService,
    shared_fake_server: fakeredis.FakeServer,
) -> None:
    publisher = fake_aioredis.FakeRedis(
        server=shared_fake_server, decode_responses=True
    )

    async def _publish_after_subscribe() -> None:
        # Give the subscriber a moment to subscribe before publishing.
        await asyncio.sleep(0.05)
        await publisher.publish("academic_pipeline_test:logs:run_xyz", "line one")
        await publisher.publish("academic_pipeline_test:logs:run_xyz", "line two")

    async def _collect() -> List[Dict[str, str]]:
        collected: List[Dict[str, str]] = []
        async for event in log_stream_service.stream("run_xyz"):
            collected.append(event)
            if event.get("event") == "status":
                break
        return collected

    publish_task = asyncio.create_task(_publish_after_subscribe())
    collected_events = await asyncio.wait_for(_collect(), timeout=10.0)
    await publish_task

    event_names = [event["event"] for event in collected_events]
    # The stream must emit at least one "log" event and exactly one
    # terminal "status" event.
    assert "log" in event_names
    assert event_names[-1] == "status"
    assert collected_events[-1]["data"] == "succeeded"
