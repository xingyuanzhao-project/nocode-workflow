"""Route test for the SSE log stream.

The route depends on a real async Redis client. We wire the app's
``LogStreamService`` to a shared fakeredis async server, seed a
terminal status in the registry, and then publish one log line
before opening the stream.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import List

import fakeredis
import pytest
from fakeredis import aioredis as fake_aioredis
from fastapi.testclient import TestClient


class _ScriptedRegistry:
    """Registry stand-in that returns ``succeeded`` after a few calls."""

    def __init__(self, flip_after: int) -> None:
        self.flip_after = flip_after
        self._calls = 0

    def get(self, run_id: str):
        from server.schemas.run import RunStatus, RunStatusDTO

        self._calls += 1
        current = (
            RunStatus.SUCCEEDED
            if self._calls > self.flip_after
            else RunStatus.RUNNING
        )
        return RunStatusDTO(run_id=run_id, status=current)


@pytest.fixture
def sse_test_client(
    test_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """Rewire ``LogStreamService`` onto a shared fakeredis instance."""
    shared_server = fakeredis.FakeServer()
    publisher = fake_aioredis.FakeRedis(server=shared_server, decode_responses=True)

    def _fake_from_url(_url: str, *, decode_responses: bool = True):
        return fake_aioredis.FakeRedis(
            server=shared_server, decode_responses=decode_responses
        )

    from server.services import log_stream as log_stream_module

    monkeypatch.setattr(log_stream_module.aioredis, "from_url", _fake_from_url)

    from server.services.log_stream import LogStreamService

    rewired_service = LogStreamService(
        async_redis_url="redis://unused/0",
        key_prefix="agent_paper_test",
        registry=_ScriptedRegistry(flip_after=2),
    )
    test_client.app.state.log_stream_service = rewired_service
    return test_client, publisher


class TestLogStreamRoute:
    def test_stream_emits_log_then_status(
        self, sse_test_client
    ) -> None:
        test_client, publisher = sse_test_client

        async def _publish_soon() -> None:
            await asyncio.sleep(0.1)
            await publisher.publish(
                "agent_paper_test:logs:run_abc", '{"level":"INFO","message":"hello"}'
            )

        # Kick off the publisher on a background asyncio loop running
        # in a separate thread so the synchronous TestClient.stream
        # call can subscribe first.
        publish_done = threading.Event()

        def _run_publish_loop() -> None:
            asyncio.run(_publish_soon())
            publish_done.set()

        publish_thread = threading.Thread(target=_run_publish_loop, daemon=True)
        publish_thread.start()

        collected_lines: List[str] = []
        with test_client.stream(
            "GET", "/api/flow/runs/run_abc/logs/stream"
        ) as response:
            assert response.status_code == 200
            for raw_line in response.iter_lines():
                collected_lines.append(raw_line)
                if raw_line.startswith("data: succeeded"):
                    break

        assert any(
            line.startswith("data: ") and "hello" in line for line in collected_lines
        )
        assert any(line.startswith("event: status") for line in collected_lines)
        publish_done.wait(timeout=5.0)
