"""Route under ``/api/flow/runs/{run_id}/logs/stream`` — live run logs.

The handler delegates every scalar responsibility to
:class:`server.services.log_stream.LogStreamService`; this file only
wires the SSE envelope expected by browsers.

Contents and relationships
--------------------------

- :data:`router` — :class:`fastapi.APIRouter` sharing the
  ``/api/flow`` prefix with :mod:`server.routes.flow` and
  :mod:`server.routes.results`.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.app` mounts :data:`router` in :func:`create_app`.
- The GUI's ``use_run_log_stream`` hook opens an
  :class:`EventSource` against this endpoint when the run page
  loads.

Invariants enforced by this module
----------------------------------

- The handler returns an
  :class:`sse_starlette.sse.EventSourceResponse`; the response
  media type (``text/event-stream``) is set by sse-starlette.
- The route never mutates state; it only reads from Redis pubsub.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from server.dependencies import get_log_stream_service
from server.services.log_stream import LogStreamService


router = APIRouter(prefix="/api/flow", tags=["logs"])
"""Router exposing the live run-log stream endpoint."""


@router.get("/runs/{run_id}/logs/stream")
async def stream_run_logs(
    run_id: str,
    service: LogStreamService = Depends(get_log_stream_service),
) -> EventSourceResponse:
    """Stream log lines for ``run_id`` as Server-Sent Events.

    Args:
        run_id (str): The run identifier whose log stream to relay.
        service (LogStreamService): Injected log-stream service.

    Returns:
        EventSourceResponse: Server-Sent Events response that emits
        one ``log`` event per record on the run's Redis pubsub
        channel, followed by one ``status`` event with the terminal
        status when the run finishes.
    """
    return EventSourceResponse(service.stream(run_id))
