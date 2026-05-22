"""JSON logging configuration for the web and worker processes.

Both the FastAPI app and the Celery worker write plain text logs by
default. On Render (and any log-aggregation system) JSON-structured lines
are easier to parse and filter, so this module replaces the root logger's
default handler with a :class:`logging.StreamHandler` backed by a JSON
formatter.

Contents and relationships
--------------------------

- :class:`JsonLogFormatter` — :class:`logging.Formatter` subclass that
  serialises each :class:`logging.LogRecord` to a single JSON line.
- :func:`configure_logging` — idempotent installer called once from
  :func:`server.app.create_app` and once per Celery worker process via
  :meth:`server.workers.signals.configure_worker_logging`.

How the rest of the system uses this module
-------------------------------------------

- The web process calls :func:`configure_logging` during app creation.
- The worker process calls :func:`configure_logging` from a Celery
  ``worker_process_init`` signal handler so each forked worker child
  gets its own formatter installed.

Invariants enforced by this module
----------------------------------

- Calling :func:`configure_logging` more than once replaces the
  formatter on existing handlers rather than stacking new handlers. This
  avoids duplicate log lines when both the app factory and a test
  fixture call it.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict


_RESERVED_LOG_RECORD_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)
"""Attribute names present on every :class:`logging.LogRecord`.

Used by :meth:`JsonLogFormatter.format` to separate caller-supplied
``extra`` fields from the stdlib's built-in attributes, so custom fields
show up at the top level of the emitted JSON line.
"""


class JsonLogFormatter(logging.Formatter):
    """Format each :class:`logging.LogRecord` as a single-line JSON object.

    Attributes:
        (none; behaviour is fully determined by :meth:`format`)

    Methods:
        format: Serialise a :class:`logging.LogRecord` into a JSON line.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Return ``record`` serialised as a single JSON line.

        Args:
            record (logging.LogRecord): The record to format.

        Returns:
            str: A JSON-encoded line ending without a trailing newline
            (``logging`` adds one itself).
        """
        payload: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info is not None:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info is not None:
            payload["stack"] = self.formatStack(record.stack_info)
        for attribute_name, attribute_value in record.__dict__.items():
            if attribute_name in _RESERVED_LOG_RECORD_ATTRIBUTES:
                continue
            if attribute_name.startswith("_"):
                continue
            payload[attribute_name] = attribute_value
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(log_level: str = "INFO") -> None:
    """Install a :class:`JsonLogFormatter` on the root logger.

    Safe to call multiple times: the function replaces the formatter on
    existing :class:`logging.StreamHandler` instances instead of adding
    new handlers, and only appends a fresh stdout handler if none is
    present.

    Args:
        log_level (str): Level name passed to
            :meth:`logging.Logger.setLevel` on the root logger. Defaults
            to ``"INFO"``.

    Returns:
        None.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level.upper())

    json_formatter = JsonLogFormatter()

    stream_handler_found = False
    for existing_handler in root_logger.handlers:
        if isinstance(existing_handler, logging.StreamHandler):
            existing_handler.setFormatter(json_formatter)
            stream_handler_found = True

    if not stream_handler_found:
        stdout_handler = logging.StreamHandler(stream=sys.stdout)
        stdout_handler.setFormatter(json_formatter)
        root_logger.addHandler(stdout_handler)
