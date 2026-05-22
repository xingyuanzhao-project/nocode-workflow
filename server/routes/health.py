"""Route under ``/api/health`` — liveness and dependency check.

Contents and relationships
--------------------------

- :data:`router` — :class:`fastapi.APIRouter` exposing
  ``GET /api/health``.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.app` mounts :data:`router` at the root.

Invariants enforced by this module
----------------------------------

- The handler pings Redis via the application-owned connection pool
  (:func:`server.redis_client.build_redis_client`) and pings the
  Celery worker pool via :meth:`celery.app.control.Inspect.ping`.
- The response status is ``"ok"`` iff both pings succeed; otherwise
  ``"degraded"``.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request

from server.redis_client import build_redis_client
from server.schemas.health import HealthResponse
from server.settings import get_settings


router = APIRouter(prefix="/api/health", tags=["health"])
"""Router exposing the health-check endpoint."""


_logger = logging.getLogger(__name__)


def _ping_redis() -> bool:
    """Return ``True`` iff a Redis ``PING`` succeeds on the app DB.

    Returns:
        bool: Liveness of the application Redis DB.
    """
    settings = get_settings()
    try:
        client = build_redis_client(settings.redis_url, settings.redis_app_db)
        return bool(client.ping())
    except Exception:  # pragma: no cover - health endpoint must not raise
        _logger.exception("redis-ping-failed")
        return False


def _ping_worker(celery_app: Any) -> bool:
    """Return ``True`` iff at least one Celery worker answers a ping.

    Args:
        celery_app (Any): The :class:`celery.Celery` instance stored on
            ``app.state.celery_app``.

    Returns:
        bool: ``True`` when at least one worker responds.
    """
    try:
        inspector = celery_app.control.inspect(timeout=1.0)
        replies = inspector.ping()
    except Exception:  # pragma: no cover - health endpoint must not raise
        _logger.exception("worker-ping-failed")
        return False
    return bool(replies)


@router.get("", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    """Return the backend's dependency health.

    Args:
        request (Request): Incoming request; used to read
            ``request.app.state.celery_app``.

    Returns:
        HealthResponse: ``status="ok"`` iff both Redis and at least
        one Celery worker respond.
    """
    redis_ok = _ping_redis()
    worker_ok = _ping_worker(request.app.state.celery_app)
    overall = "ok" if redis_ok and worker_ok else "degraded"
    return HealthResponse(status=overall, redis_ok=redis_ok, worker_ok=worker_ok)
