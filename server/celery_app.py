"""Celery application factory for the agent_paper worker process.

Constructs the single :class:`celery.Celery` instance imported by both
the web process (which calls :meth:`Celery.send_task`) and the worker
process (which is launched as
``celery -A server.celery_app worker --pool=solo``). Every tunable on
the Celery app is read from :class:`server.settings.ServerSettings`; no
magic numbers live in this module.

Contents and relationships
--------------------------

- :data:`celery_app` — the shared :class:`celery.Celery` instance.
  Configured with:

  - ``broker_url`` and ``result_backend`` assembled from
    :func:`server.settings.broker_url` and
    :func:`server.settings.result_backend_url` so the broker queue and
    the result cache live on separate Redis logical DBs.
  - ``task_acks_late=True`` so a crashed worker's task is requeued by
    the broker instead of silently lost.
  - ``task_reject_on_worker_lost=True`` so a SIGKILL'd worker returns
    its in-flight task to the queue.
  - ``worker_prefetch_multiplier=1`` so a worker pulls one long-running
    task at a time.
  - ``task_serializer="json"`` and ``accept_content=["json"]`` (no
    pickle).
  - ``result_expires=settings.celery_result_expires`` so completed
    Celery result entries are GC'd.
  - ``worker_shutdown_timeout=settings.worker_shutdown_timeout`` so
    SIGTERM gives a bounded grace period.

  Task modules are registered via the ``include`` constructor
  argument. :mod:`server.workers.flow_task` is listed explicitly so
  both the web process (which sends tasks by name) and the worker
  process (which executes them) agree on the task registry. The
  signal handlers in :mod:`server.workers.signals` are imported at
  module end so they register with the shared instance whenever this
  module is imported (by either the web process or the worker
  process).

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.services.run_dispatcher` imports :data:`celery_app` and
  calls :meth:`Celery.send_task` by name, never by direct task-object
  reference, so the dispatcher does not import from
  :mod:`server.workers`.
- The worker entrypoint is
  ``celery -A server.celery_app worker --pool=solo --concurrency=1``.

Invariants enforced by this module
----------------------------------

- Exactly one :class:`celery.Celery` instance per process.
- No hard-coded tunable values in this module; every setting reads
  through :func:`server.settings.get_settings`.
- The worker pool is ``solo`` (single-threaded, single-process per
  container). Horizontal scaling happens by running additional worker
  containers, not by increasing in-process concurrency. The task body
  owns its own asyncio event loop via :func:`asyncio.run`, which is
  compatible with ``solo`` but not with ``prefork`` or ``gevent``.
"""

from __future__ import annotations

from celery import Celery

from server.settings import broker_url, get_settings, result_backend_url


def _build_celery_app() -> Celery:
    """Construct the process-wide :class:`celery.Celery` instance.

    Every tunable is read from :func:`server.settings.get_settings`.

    Returns:
        Celery: The configured Celery application.
    """
    settings = get_settings()
    application = Celery(
        "agent_paper",
        broker=broker_url(settings),
        backend=result_backend_url(settings),
        include=["server.workers.flow_task"],
    )
    application.conf.update(
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        result_expires=settings.celery_result_expires,
        worker_shutdown_timeout=settings.worker_shutdown_timeout,
        timezone="UTC",
        enable_utc=True,
        broker_connection_retry_on_startup=True,
    )
    return application


celery_app: Celery = _build_celery_app()
"""The shared Celery application. Imported by the dispatcher service
and by the worker entrypoint."""


# Register Celery signal handlers by importing the signals module. The
# import must happen after ``celery_app`` is defined so the handlers
# can reference it. ``noqa: E402`` would be needed if any linter is run
# with strict top-level-only import ordering; the import order here is
# deliberate and documented.
from server.workers import signals as _signals  # noqa: E402, F401
