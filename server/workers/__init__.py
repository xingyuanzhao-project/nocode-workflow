"""Celery task bodies and signal handlers.

The :mod:`server.workers` package is imported only by the worker
process (via :meth:`celery.Celery.autodiscover_tasks` in
:mod:`server.celery_app`). The web process never imports from here;
its only coupling point is
:data:`server.services.run_dispatcher.FLOW_TASK_NAME`, the task name
string passed to :meth:`celery.Celery.send_task`.

Module layout
-------------

- :mod:`server.workers.flow_task` — the task body that calls
  :func:`src.flow_builder.build_flow` and runs the flow.
- :mod:`server.workers.signals` — Celery signal handlers that mutate
  :class:`server.services.run_registry.RunRegistry` when tasks
  transition state, and that manage the
  :data:`server.workers.redis_log_handler.CURRENT_RUN_ID` contextvar
  for the live log stream.
- :mod:`server.workers.redis_log_handler` —
  :class:`logging.Handler` that publishes log records to a Redis
  pubsub channel; subscribed to by
  :mod:`server.services.log_stream` in the web process.
"""
