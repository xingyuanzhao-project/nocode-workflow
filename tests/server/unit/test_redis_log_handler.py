"""Unit tests for :class:`server.workers.redis_log_handler.RedisLogHandler`.

The handler is the piece that routes worker log records to Redis
pubsub so the SSE endpoint can relay them. Tests cover the three
documented branches: contextvar unset, contextvar set, publish
failure.
"""

from __future__ import annotations

import logging
from typing import List

import pytest

from server.workers.redis_log_handler import (
    CURRENT_RUN_ID,
    RedisLogHandler,
    build_log_channel_name,
    reset_current_run_id,
    set_current_run_id,
)


class _FakePublishingRedis:
    """Minimal Redis stand-in recording publish calls.

    Attributes:
        published (List[Tuple[str, str]]): Every ``(channel, message)``
            pair passed to :meth:`publish`.
        raise_on_publish (bool): When ``True`` every
            :meth:`publish` call raises.
    """

    def __init__(self) -> None:
        self.published: List[tuple[str, str]] = []
        self.raise_on_publish: bool = False

    def publish(self, channel: str, message: str) -> int:
        if self.raise_on_publish:
            raise RuntimeError("publish failed")
        self.published.append((channel, message))
        return 1


def _make_log_record(message: str = "hello world") -> logging.LogRecord:
    """Return a minimal :class:`logging.LogRecord` for :meth:`emit` tests.

    Args:
        message (str): Message body.

    Returns:
        logging.LogRecord: A fresh record at INFO level.
    """
    return logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


class TestRedisLogHandlerContextvar:
    def test_emit_noop_when_current_run_id_unset(self) -> None:
        fake_redis = _FakePublishingRedis()
        handler = RedisLogHandler(redis_client=fake_redis, key_prefix="prefix")
        handler.emit(_make_log_record())
        assert fake_redis.published == []

    def test_emit_publishes_on_contextvar_channel(self) -> None:
        fake_redis = _FakePublishingRedis()
        handler = RedisLogHandler(redis_client=fake_redis, key_prefix="prefix")
        handler.setFormatter(logging.Formatter("%(levelname)s|%(message)s"))
        token = set_current_run_id("run_xyz")
        try:
            handler.emit(_make_log_record("line one"))
        finally:
            reset_current_run_id(token)
        assert len(fake_redis.published) == 1
        channel, message = fake_redis.published[0]
        assert channel == "prefix:logs:run_xyz"
        assert message == "INFO|line one"

    def test_reset_restores_previous_token(self) -> None:
        assert CURRENT_RUN_ID.get() is None
        token = set_current_run_id("outer")
        reset_current_run_id(token)
        assert CURRENT_RUN_ID.get() is None


class TestRedisLogHandlerPublishFailure:
    def test_publish_failure_is_routed_through_handle_error(self) -> None:
        fake_redis = _FakePublishingRedis()
        fake_redis.raise_on_publish = True
        handler = RedisLogHandler(redis_client=fake_redis, key_prefix="prefix")
        observed: List[logging.LogRecord] = []
        handler.handleError = lambda record: observed.append(record)  # type: ignore[method-assign]
        token = set_current_run_id("run_xyz")
        try:
            handler.emit(_make_log_record("boom"))
        finally:
            reset_current_run_id(token)
        assert len(observed) == 1
        assert observed[0].getMessage() == "boom"


class TestBuildLogChannelName:
    def test_format_matches_subscriber_expectation(self) -> None:
        assert build_log_channel_name("prefix", "runid") == "prefix:logs:runid"
