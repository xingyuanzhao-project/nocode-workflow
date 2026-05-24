"""HTTP DTOs for the run lifecycle endpoints.

Contents and relationships
--------------------------

- :class:`RunStatus` — closed enum describing a run's position in the
  lifecycle. Mirrored in
  :class:`server.services.run_registry.RunRegistry` as the ``status``
  field stored on the Redis hash.
- :class:`RunStartResponse` — response of ``POST /api/flow/run`` and
  ``POST /api/flow/{id}/run``.
- :class:`RunStatusDTO` — response of ``GET /api/flow/status/{run_id}``.

How the rest of the system uses this module
-------------------------------------------

- :class:`server.services.run_dispatcher.RunDispatcher` returns
  :class:`RunStartResponse` from both :meth:`RunDispatcher.submit` and
  :meth:`RunDispatcher.resume`.
- :class:`server.services.run_registry.RunRegistry` returns
  :class:`RunStatusDTO` from :meth:`RunRegistry.get`.
- :mod:`server.workers.signals` writes :class:`RunStatus` values via
  the registry.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class RunStatus(str, Enum):
    """Closed enum of run lifecycle positions.

    ``queued`` — enqueued by
    :class:`server.services.run_dispatcher.RunDispatcher`, not yet
    picked up by a worker.
    ``running`` — the Celery task is executing (set by
    :meth:`server.workers.signals.on_task_prerun`).
    ``succeeded`` — the task finished without raising (set by
    :meth:`server.workers.signals.on_task_success`).
    ``failed`` — the task raised an exception (set by
    :meth:`server.workers.signals.on_task_failure`).
    ``cancelled`` — the user revoked the run (future work; reserved
    here for wire compatibility).
    """

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunStartResponse(BaseModel):
    """Response of ``POST /api/flow/run``, ``POST /api/flow/{id}/run``, and ``POST /api/flow/resume/{run_id}``.

    Attributes:
        run_id (str): Identifier assigned by
            :class:`server.services.run_dispatcher.RunDispatcher` for
            fresh runs, or echoed back for resume calls.
        status (RunStatus): Initial status. Always
            :attr:`RunStatus.QUEUED` immediately after enqueue.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: RunStatus = RunStatus.QUEUED


class RunStatusDTO(BaseModel):
    """Response of ``GET /api/flow/status/{run_id}``.

    Attributes:
        run_id (str): The queried run identifier.
        status (RunStatus): Current lifecycle position.
        started_at (Optional[str]): ISO-8601 timestamp when the task
            first transitioned to :attr:`RunStatus.RUNNING`. ``None``
            while still :attr:`RunStatus.QUEUED`.
        finished_at (Optional[str]): ISO-8601 timestamp when the task
            reached a terminal state. ``None`` for non-terminal states.
        error (Optional[str]): Short error message captured by
            :meth:`server.workers.signals.on_task_failure`. ``None``
            unless :attr:`status` is :attr:`RunStatus.FAILED`.
        completed_entity_count (int): Number of entity ids listed in
            the run's ``completed_entities.json`` file. ``0`` when the
            checkpoint file does not yet exist.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: RunStatus
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None
    warnings: List[str] = []
    completed_entity_count: int = 0
    total_row_count: int = 0


class RunListItem(BaseModel):
    """One entry in the ``GET /api/flow/runs`` list response.

    Attributes:
        run_id (str): The run identifier.
        status (RunStatus): Current lifecycle position.
        started_at (Optional[str]): ISO-8601 timestamp when the task
            started running. ``None`` if still queued.
        finished_at (Optional[str]): ISO-8601 timestamp when the task
            finished. ``None`` if not yet terminal.
        flow_name (Optional[str]): Display name extracted from the
            run's flow YAML, if available.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: RunStatus
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    flow_name: Optional[str] = None
