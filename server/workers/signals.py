"""Celery signal handlers that mutate :class:`RunRegistry` on task events.

Moves run-status updates out of the task body in
:mod:`server.workers.flow_task` so the task itself stays focused on
"load the flow YAML, run the flow". Every lifecycle transition
(``prerun``, ``success``, ``failure``) maps to exactly one Redis
mutation, and the same ``prerun`` / ``postrun`` pair also manages the
:data:`server.workers.redis_log_handler.CURRENT_RUN_ID` contextvar so
logs emitted during the task body land on the correct pubsub channel.

Contents and relationships
--------------------------

- :func:`on_task_prerun` — calls
  :meth:`server.services.run_registry.RunRegistry.mark_running` and
  binds :data:`CURRENT_RUN_ID` so the log handler publishes to the
  right channel.
- :func:`on_task_postrun` — resets :data:`CURRENT_RUN_ID` after the
  task body finishes (whether by success or failure).
- :func:`on_task_success` — calls
  :meth:`RunRegistry.mark_succeeded` after a successful run.
- :func:`on_task_failure` — calls :meth:`RunRegistry.mark_failed` with
  a truncated exception repr.
- :func:`on_worker_process_init` — installs the JSON logger *and* the
  :class:`RedisLogHandler` in every forked worker child.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.celery_app` imports this module at the end of its
  factory so the ``@signal.connect`` decorators register against the
  shared :class:`celery.Celery` instance whenever the module is
  imported (web or worker process).

Invariants enforced by this module
----------------------------------

- Handlers filter by :data:`TARGETED_TASK_NAME` so unrelated future
  tasks do not mutate the run registry or the logging contextvar.
- The :class:`server.services.run_registry.RunRegistry` instance is
  built lazily on first use and memoised per worker process, so the
  web process (which also imports :mod:`server.celery_app`) never
  opens an unnecessary Redis connection pool.
- Exception messages stored via :meth:`RunRegistry.mark_failed` are
  truncated to :data:`_MAX_ERROR_LENGTH` characters so a multi-line
  traceback does not bloat the Redis hash.
- The :class:`RedisLogHandler` is attached exactly once per process
  (guarded by :data:`_redis_log_handler_installed`). Double-attaching
  would cause every log line to be published twice.
- The contextvar token from :func:`set_current_run_id` is stashed on
  the task instance (``task.request.academic_pipeline_run_id_token``) so
  :func:`on_task_postrun` can reset the correct token even when the
  task runs in a different context from the signal dispatcher.
"""

from __future__ import annotations

import logging
from contextvars import Token
from typing import Any, Optional

from celery.signals import (
    task_failure,
    task_postrun,
    task_prerun,
    task_success,
    worker_process_init,
)

from server.logging_config import JsonLogFormatter, configure_logging
from server.redis_client import build_redis_client
from server.services.run_registry import RunRegistry, build_run_registry
from server.settings import ServerSettings, get_settings
from server.storage.paths import ServerPaths
from server.workers.redis_log_handler import (
    RedisLogHandler,
    reset_current_run_id,
    set_current_run_id,
)


TARGETED_TASK_NAME: str = "server.workers.flow_task.execute_flow"
"""Name of the task whose lifecycle this module tracks. Duplicated as a
string rather than imported from :mod:`server.workers.flow_task` so
this module can be loaded from the Celery app factory before the task
module is imported."""


_MAX_ERROR_LENGTH: int = 2000
"""Upper bound on the characters stored in
:class:`server.services.run_registry.RunRegistry`'s ``error`` field."""


_RUN_ID_TOKEN_ATTRIBUTE: str = "academic_pipeline_run_id_token"
"""Attribute name used to stash the contextvar reset token on the task
request. See :func:`on_task_prerun` and :func:`on_task_postrun`."""


_registry_instance: Optional[RunRegistry] = None
"""Per-process memoised registry. Lazily populated by
:func:`_get_registry`."""


_redis_log_handler_installed: bool = False
"""Guard flag for :func:`_attach_redis_log_handler`.

Ensures a single :class:`RedisLogHandler` is attached per process even
if :func:`on_worker_process_init` runs more than once (for example in
tests that reuse the same interpreter)."""


_logger = logging.getLogger(__name__)


def _get_registry() -> RunRegistry:
    """Return the per-process :class:`RunRegistry` instance.

    The web process and every forked worker child get their own
    instance on first call.

    Returns:
        RunRegistry: The cached instance for this process.
    """
    global _registry_instance
    if _registry_instance is None:
        settings = get_settings()
        paths = ServerPaths.from_settings(settings)
        _registry_instance = build_run_registry(paths, settings)
    return _registry_instance


def _attach_redis_log_handler(settings: ServerSettings) -> None:
    """Attach a :class:`RedisLogHandler` to the root logger once.

    Idempotent: guarded by :data:`_redis_log_handler_installed`. The
    handler uses a fresh :class:`redis.Redis` client bound to the
    application DB (the same DB the SSE route subscribes on).

    Args:
        settings (ServerSettings): Process settings supplying the
            Redis URL, app DB index, and key prefix.

    Returns:
        None.
    """
    global _redis_log_handler_installed
    if _redis_log_handler_installed:
        return
    redis_client = build_redis_client(settings.redis_url, settings.redis_app_db)
    handler = RedisLogHandler(
        redis_client=redis_client,
        key_prefix=settings.redis_key_prefix,
    )
    handler.setFormatter(JsonLogFormatter())
    logging.getLogger().addHandler(handler)
    _redis_log_handler_installed = True


def _extract_run_id(task_args: Any, task_kwargs: Any) -> Optional[str]:
    """Return the first positional argument if it looks like a run id.

    The task signature is ``execute_flow(run_id: str)``, so the run id
    is either ``args[0]`` or ``kwargs["run_id"]``. Returns ``None``
    when neither is available (for example when Celery emits a signal
    for an unrelated task type).

    Args:
        task_args (Any): ``args`` kwarg from the Celery signal.
        task_kwargs (Any): ``kwargs`` kwarg from the Celery signal.

    Returns:
        Optional[str]: The run id when resolvable.
    """
    if isinstance(task_kwargs, dict) and "run_id" in task_kwargs:
        return str(task_kwargs["run_id"])
    if isinstance(task_args, (list, tuple)) and task_args:
        return str(task_args[0])
    return None


@task_prerun.connect
def on_task_prerun(
    sender=None,
    task_id=None,
    task=None,
    args=None,
    kwargs=None,
    **_ignored,
) -> None:
    """Mark the run ``running`` and bind :data:`CURRENT_RUN_ID`.

    The contextvar binding is done here (not in the task body) so
    :class:`RedisLogHandler` sees the correct ``run_id`` even for
    log records emitted by module-level imports or other signal
    handlers triggered during task execution.

    Args:
        sender: Unused; provided by Celery.
        task_id: Celery task id (unused here; the run id is what the
            application tracks).
        task: The :class:`celery.Task` instance; used to filter by
            name and to stash the contextvar reset token under
            :data:`_RUN_ID_TOKEN_ATTRIBUTE`.
        args: Positional args the task was called with.
        kwargs: Keyword args the task was called with.
        **_ignored: Additional Celery-supplied kwargs we do not read.

    Returns:
        None.
    """
    if task is None or task.name != TARGETED_TASK_NAME:
        return
    run_id = _extract_run_id(args, kwargs)
    if run_id is None:
        return
    _get_registry().mark_running(run_id)

    reset_token: Token = set_current_run_id(run_id)
    request = getattr(task, "request", None)
    if request is not None:
        setattr(request, _RUN_ID_TOKEN_ATTRIBUTE, reset_token)


@task_postrun.connect
def on_task_postrun(
    sender=None,
    task_id=None,
    task=None,
    args=None,
    kwargs=None,
    retval=None,
    state=None,
    **_ignored,
) -> None:
    """Reset :data:`CURRENT_RUN_ID` after the task body finishes.

    Runs regardless of success or failure, so no task can leak its
    ``run_id`` into a subsequent task's log stream.

    Args:
        sender: Unused; provided by Celery.
        task_id: Celery task id (unused).
        task: The :class:`celery.Task` instance; used to filter by
            name and retrieve the contextvar reset token stashed by
            :func:`on_task_prerun`.
        args: Positional args the task was called with.
        kwargs: Keyword args the task was called with.
        retval: Task return value (unused).
        state: Final Celery state (unused).
        **_ignored: Additional Celery-supplied kwargs we do not read.

    Returns:
        None.
    """
    if task is None or task.name != TARGETED_TASK_NAME:
        return
    request = getattr(task, "request", None)
    if request is None:
        return
    reset_token = getattr(request, _RUN_ID_TOKEN_ATTRIBUTE, None)
    if reset_token is None:
        return
    reset_current_run_id(reset_token)
    setattr(request, _RUN_ID_TOKEN_ATTRIBUTE, None)


@task_success.connect
def on_task_success(sender=None, **_ignored) -> None:
    """Mark the run as ``succeeded`` after a clean task return.

    Args:
        sender: The :class:`celery.Task` instance; used to filter by
            name and to read its invocation ``args`` / ``kwargs``.
        **_ignored: Additional Celery-supplied kwargs we do not read.

    Returns:
        None.
    """
    if sender is None or getattr(sender, "name", None) != TARGETED_TASK_NAME:
        return
    invocation = getattr(sender, "request", None)
    if invocation is None:
        return
    run_id = _extract_run_id(
        getattr(invocation, "args", None),
        getattr(invocation, "kwargs", None),
    )
    if run_id is None:
        return
    _get_registry().mark_succeeded(run_id)


@task_failure.connect
def on_task_failure(
    sender=None,
    task_id=None,
    exception=None,
    args=None,
    kwargs=None,
    **_ignored,
) -> None:
    """Mark the run as ``failed`` and record a truncated error message.

    Args:
        sender: The :class:`celery.Task` instance; used to filter by
            name.
        task_id: Celery task id (unused).
        exception: The exception the task raised.
        args: Positional args the task was called with.
        kwargs: Keyword args the task was called with.
        **_ignored: Additional Celery-supplied kwargs we do not read.

    Returns:
        None.
    """
    if sender is None or getattr(sender, "name", None) != TARGETED_TASK_NAME:
        return
    run_id = _extract_run_id(args, kwargs)
    if run_id is None:
        return
    error_message = repr(exception)[:_MAX_ERROR_LENGTH] if exception else ""
    _get_registry().mark_failed(run_id, error_message)


@worker_process_init.connect
def on_worker_process_init(**_ignored) -> None:
    """Install the JSON logger and :class:`RedisLogHandler` in every forked child.

    Args:
        **_ignored: Celery-supplied kwargs we do not read.

    Returns:
        None.
    """
    settings = get_settings()
    configure_logging(settings.log_level)
    _attach_redis_log_handler(settings)
    _logger.info("worker-process-init")
