"""HTTP DTO for the health-check endpoint.

Contents and relationships
--------------------------

- :class:`HealthResponse` — response of ``GET /api/health``.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.routes.health` builds one of these from a Redis ping
  and a Celery worker-inspect call.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Summary of the backend's dependency health.

    Attributes:
        status (Literal["ok", "degraded"]): ``"ok"`` iff both
            :attr:`redis_ok` and :attr:`worker_ok` are ``True``;
            ``"degraded"`` otherwise.
        redis_ok (bool): ``True`` iff a Redis ``PING`` succeeds against
            the application-owned Redis DB.
        worker_ok (bool): ``True`` iff at least one Celery worker
            responds to ``celery.control.inspect().ping()`` within the
            route-configured timeout.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "degraded"]
    redis_ok: bool
    worker_ok: bool
