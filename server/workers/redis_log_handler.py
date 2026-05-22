"""Logging handler that publishes log records to a Redis pubsub channel.

The GUI streams a run's logs live over Server-Sent Events. The
worker side of that stream is this handler: attached to the root
logger in every Celery worker process, it reads the currently-running
``run_id`` from a :class:`contextvars.ContextVar` set by
:mod:`server.workers.signals` and publishes each log record as one
message on ``{redis_key_prefix}:logs:{run_id}`` in the application
Redis DB.

Using Redis pubsub (not file tailing) means:

- The web process can subscribe from any container (not just the
  worker's local disk).
- Log lines survive log-file rotation because they are a side channel.
- Multiple web replicas each see every subscriber event.

Contents and relationships
--------------------------

- :class:`RedisLogHandler` — the :class:`logging.Handler` subclass.
- :data:`CURRENT_RUN_ID` — the :class:`contextvars.ContextVar` that
  carries the active ``run_id`` through the synchronous signal
  handler and into the :func:`asyncio.run` body of the task.
- :func:`set_current_run_id` / :func:`reset_current_run_id` —
  thin wrappers the Celery signal handlers use to manage the
  contextvar lifetime.
- :func:`build_log_channel_name` — single place that knows how a
  ``run_id`` translates into a Redis pubsub channel name. The SSE
  route in :mod:`server.routes.logs` imports this helper so both
  sides agree on the channel shape.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.workers.signals` attaches the handler on every forked
  worker child (``worker_process_init``) and manages the
  contextvar's lifetime (``task_prerun`` / ``task_postrun``).
- :mod:`server.services.log_stream` and :mod:`server.routes.logs`
  subscribe to the same channel from the web process and relay the
  messages to the browser over SSE.

Invariants enforced by this module
----------------------------------

- The handler is *no-op* when :data:`CURRENT_RUN_ID` is unset
  (contextvar default is ``None``). This keeps startup noise out of
  Redis and avoids cross-talk between runs that briefly overlap in
  the same process.
- Publish failures do not propagate into the calling code; they are
  routed through :meth:`logging.Handler.handleError` the same way
  every other logging handler handles backend failures.
- The channel name is always constructed through
  :func:`build_log_channel_name` — no ad-hoc f-strings in callers.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar, Token
from typing import Optional

import redis


CURRENT_RUN_ID: ContextVar[Optional[str]] = ContextVar(
    "agent_paper_current_run_id",
    default=None,
)
"""Active run identifier for the current execution context.

Set by :func:`server.workers.signals.on_task_prerun` immediately
before the Celery task body runs and reset by
:func:`server.workers.signals.on_task_postrun`. Python's
:mod:`contextvars` semantics guarantee the value is visible inside
the task's :func:`asyncio.run` event loop because ``asyncio.run``
copies the current context for its top-level coroutine.
"""


def set_current_run_id(run_id: str) -> Token[Optional[str]]:
    """Bind ``run_id`` to :data:`CURRENT_RUN_ID` and return the token.

    The token should be passed to :func:`reset_current_run_id` in a
    ``finally`` block (or in the paired ``task_postrun`` handler) so
    the contextvar is restored to its previous value.

    Args:
        run_id (str): The run identifier to set.

    Returns:
        Token[Optional[str]]: Token produced by
        :meth:`ContextVar.set`, used to reset the contextvar later.
    """
    return CURRENT_RUN_ID.set(run_id)


def reset_current_run_id(token: Token[Optional[str]]) -> None:
    """Reset :data:`CURRENT_RUN_ID` using the token from :func:`set_current_run_id`.

    Args:
        token (Token[Optional[str]]): The token returned by
            :func:`set_current_run_id`.

    Returns:
        None.
    """
    CURRENT_RUN_ID.reset(token)


def build_log_channel_name(key_prefix: str, run_id: str) -> str:
    """Return the Redis pubsub channel name for ``run_id``.

    Centralising the channel-name format here ensures the worker's
    publisher and the web process's SSE subscriber (in
    :mod:`server.routes.logs`) always agree.

    Args:
        key_prefix (str): The application key prefix (matches
            :attr:`server.settings.ServerSettings.redis_key_prefix`).
        run_id (str): The run identifier.

    Returns:
        str: ``f"{key_prefix}:logs:{run_id}"``.
    """
    return f"{key_prefix}:logs:{run_id}"


class RedisLogHandler(logging.Handler):
    """Publish every log record to ``{key_prefix}:logs:{run_id}``.

    Attributes:
        redis_client (redis.Redis): Synchronous Redis client used for
            ``PUBLISH``. The client must be bound to the same logical
            DB the web process subscribes on (see
            :attr:`server.settings.ServerSettings.redis_app_db`).
        key_prefix (str): Application key prefix applied to the
            channel name.

    Methods:
        emit: Called by the logging machinery for every accepted
            record. Publishes the formatted record to the Redis
            channel for the currently-active run.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        key_prefix: str,
        level: int = logging.INFO,
    ) -> None:
        """Store the Redis client and key prefix and set the handler level.

        Args:
            redis_client (redis.Redis): Synchronous Redis client.
            key_prefix (str): Application key prefix.
            level (int): Minimum level the handler forwards to Redis.
                Defaults to :data:`logging.INFO` so DEBUG chatter does
                not flood the SSE stream.
        """
        super().__init__(level=level)
        self.redis_client = redis_client
        self.key_prefix = key_prefix

    def emit(self, record: logging.LogRecord) -> None:
        """Publish ``record`` to the pubsub channel for the active run.

        Args:
            record (logging.LogRecord): The record to publish.

        Returns:
            None.
        """
        active_run_id = CURRENT_RUN_ID.get()
        if active_run_id is None:
            return
        try:
            formatted_line = self.format(record)
            channel_name = build_log_channel_name(self.key_prefix, active_run_id)
            self.redis_client.publish(channel_name, formatted_line)
        except Exception:  # pragma: no cover - routed through handleError
            self.handleError(record)


__all__ = [
    "CURRENT_RUN_ID",
    "RedisLogHandler",
    "build_log_channel_name",
    "reset_current_run_id",
    "set_current_run_id",
]
