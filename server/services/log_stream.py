"""Web-side service that streams a run's logs from the Redis pubsub channel.

The worker publishes one log record per ``PUBLISH`` call on
``{key_prefix}:logs:{run_id}`` via
:class:`server.workers.redis_log_handler.RedisLogHandler`. This service
is the web-side subscriber: it opens an async pubsub connection to the
same channel and yields each received message as a Server-Sent Events
dict suitable for :class:`sse_starlette.sse.EventSourceResponse`.

Contents and relationships
--------------------------

- :class:`LogStreamService` — the service.
- :data:`_LOG_EVENT_NAME` / :data:`_STATUS_EVENT_NAME` — SSE event
  names yielded by :meth:`LogStreamService.stream`.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.routes.logs` calls :meth:`LogStreamService.stream` from
  the ``GET /api/flow/runs/{run_id}/logs/stream`` handler and wraps
  the result in :class:`sse_starlette.sse.EventSourceResponse`.
- :mod:`server.dependencies` provides the singleton via
  ``request.app.state.log_stream_service``, constructed once in
  :func:`server.app.create_app`.

Invariants enforced by this module
----------------------------------

- The generator always yields a terminal status event (named
  :data:`_STATUS_EVENT_NAME`) before returning, so the GUI can
  display the final status even if no log lines were produced.
- The generator polls the run registry every
  :data:`_STATUS_POLL_INTERVAL_SECONDS` seconds so it terminates
  within that window after the run reaches a terminal state.
- The subscribed pubsub connection is closed in a ``finally`` block
  regardless of how the generator exits (normal completion, client
  disconnect, exception).
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, Dict, Optional

import redis.asyncio as aioredis

from server.schemas.run import RunStatus
from server.services.run_registry import RunRegistry
from server.settings import ServerSettings, app_redis_url
from server.workers.redis_log_handler import build_log_channel_name


_LOG_EVENT_NAME: str = "log"
"""SSE event name used for each log record relayed from Redis."""


_STATUS_EVENT_NAME: str = "status"
"""SSE event name used for the terminal run-status event."""


_STATUS_POLL_INTERVAL_SECONDS: float = 1.0
"""How often the generator polls the run registry for a terminal status.

Kept at one second so the stream closes promptly after the worker
marks the run done without flooding Redis with ``HGET`` calls.
"""


_MESSAGE_WAIT_TIMEOUT_SECONDS: float = 0.5
"""Per-iteration timeout of ``pubsub.get_message``.

Controls how often the generator loops around to check the run
registry. Smaller values close the SSE stream faster after the run
finishes at the cost of more CPU; half a second is a comfortable
compromise.
"""


_TERMINAL_RUN_STATUSES = frozenset(
    {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}
)
"""Run statuses at which :meth:`LogStreamService.stream` returns."""


_logger = logging.getLogger(__name__)


class LogStreamService:
    """Relay a run's log records from Redis pubsub to the SSE generator.

    Attributes:
        async_redis_url (str): The application-owned Redis URL
            (``<redis_url>/<redis_app_db>``). Each call to
            :meth:`stream` opens its own :class:`aioredis.Redis`
            client against this URL so per-client subscriber state
            is isolated.
        key_prefix (str): Application key prefix used to build the
            pubsub channel name.
        registry (RunRegistry): Synchronous registry service consulted
            for terminal status checks.

    Methods:
        stream: Async generator yielding SSE events for one run.
    """

    def __init__(
        self,
        async_redis_url: str,
        key_prefix: str,
        registry: RunRegistry,
    ) -> None:
        """Store the injected Redis URL, key prefix, and registry.

        Args:
            async_redis_url (str): Application-owned Redis URL.
            key_prefix (str): Application key prefix.
            registry (RunRegistry): The run registry service.
        """
        self.async_redis_url = async_redis_url
        self.key_prefix = key_prefix
        self.registry = registry

    async def stream(self, run_id: str) -> AsyncIterator[Dict[str, str]]:
        """Yield SSE events for ``run_id``'s log channel until terminal.

        Each yielded dict is the shape
        :class:`sse_starlette.sse.EventSourceResponse` expects:
        ``{"event": <name>, "data": <payload>}``. Two event names
        are emitted:

        - :data:`_LOG_EVENT_NAME` — one per log record received on
          the pubsub channel, with the formatted line in ``data``.
        - :data:`_STATUS_EVENT_NAME` — emitted exactly once, just
          before the generator returns, with the terminal status
          string (``succeeded`` / ``failed`` / ``cancelled``).

        Args:
            run_id (str): The run identifier whose logs to stream.

        Yields:
            Dict[str, str]: SSE event payload.
        """
        channel_name = build_log_channel_name(self.key_prefix, run_id)
        redis_client = aioredis.from_url(
            self.async_redis_url, decode_responses=True
        )
        pubsub = redis_client.pubsub()
        try:
            await pubsub.subscribe(channel_name)
            while True:
                terminal_status = self._peek_terminal_status(run_id)
                if terminal_status is not None:
                    # Drain any log records published between the last
                    # poll and the terminal status before closing so
                    # the client does not miss the tail of the log.
                    async for drained_event in self._drain_pubsub(pubsub):
                        yield drained_event
                    yield {
                        "event": _STATUS_EVENT_NAME,
                        "data": terminal_status.value,
                    }
                    return

                raw_message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=_MESSAGE_WAIT_TIMEOUT_SECONDS,
                )
                if raw_message is None:
                    await asyncio.sleep(0)
                    continue
                message_payload = raw_message.get("data")
                if not isinstance(message_payload, str):
                    continue
                yield {"event": _LOG_EVENT_NAME, "data": message_payload}
        finally:
            try:
                await pubsub.unsubscribe(channel_name)
            except Exception:  # pragma: no cover - best-effort cleanup
                _logger.debug(
                    "unsubscribe failed on channel %s", channel_name
                )
            try:
                await pubsub.aclose()
            except Exception:  # pragma: no cover - best-effort cleanup
                _logger.debug(
                    "pubsub aclose failed on channel %s", channel_name
                )
            try:
                await redis_client.aclose()
            except Exception:  # pragma: no cover - best-effort cleanup
                _logger.debug(
                    "redis client aclose failed on channel %s", channel_name
                )

    def _peek_terminal_status(self, run_id: str) -> Optional[RunStatus]:
        """Return the terminal status for ``run_id`` or ``None``.

        Wraps the synchronous :meth:`RunRegistry.get` call so
        registry lookups stay inside this module. Returns ``None``
        when the registry entry is missing or the status is still
        non-terminal.

        Args:
            run_id (str): The run identifier.

        Returns:
            Optional[RunStatus]: Terminal status when the run has
            reached ``succeeded`` / ``failed`` / ``cancelled``,
            ``None`` otherwise.
        """
        try:
            status_dto = self.registry.get(run_id)
        except FileNotFoundError:
            return None
        if status_dto.status in _TERMINAL_RUN_STATUSES:
            return status_dto.status
        return None

    @staticmethod
    async def _drain_pubsub(
        pubsub: aioredis.client.PubSub,
    ) -> AsyncIterator[Dict[str, str]]:
        """Yield every already-buffered log record on ``pubsub``.

        Returns promptly once ``get_message`` times out with
        ``None``; used to flush the channel's tail before closing
        the SSE stream.

        Args:
            pubsub (aioredis.client.PubSub): The active subscription.

        Yields:
            Dict[str, str]: SSE event payload.
        """
        while True:
            raw_message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=0.0,
            )
            if raw_message is None:
                return
            message_payload = raw_message.get("data")
            if not isinstance(message_payload, str):
                continue
            yield {"event": _LOG_EVENT_NAME, "data": message_payload}


def build_log_stream_service(
    settings: ServerSettings, registry: RunRegistry
) -> LogStreamService:
    """Construct a :class:`LogStreamService` from settings and registry.

    Args:
        settings (ServerSettings): Process settings supplying the
            Redis URL, app DB index, and key prefix.
        registry (RunRegistry): The registry the stream polls.

    Returns:
        LogStreamService: The ready-to-use service.
    """
    return LogStreamService(
        async_redis_url=app_redis_url(settings),
        key_prefix=settings.redis_key_prefix,
        registry=registry,
    )


__all__ = [
    "LogStreamService",
    "build_log_stream_service",
]
