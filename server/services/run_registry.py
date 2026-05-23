"""Redis-backed store of run status, shared by web and worker processes.

Every run created by
:class:`server.services.run_dispatcher.RunDispatcher` gets a hash in
the application Redis DB keyed by
``f"{settings.redis_key_prefix}:run:{run_id}"``. The hash is read by
``GET /api/flow/status/{run_id}`` and written by the Celery signal
handlers in :mod:`server.workers.signals`. Terminal entries receive a
TTL so completed runs are GC'd on the same cadence as their Celery
result backend entries.

The registry is a :class:`server.schemas.run.RunStatus` store; it is
not the Celery result backend. Keeping the two concerns separate means
the user-visible status survives Celery result-backend TTL expiry until
the application TTL also fires.

Contents and relationships
--------------------------

- :class:`RunRegistry` — service holding a :class:`redis.Redis` client
  and a :class:`server.storage.paths.ServerPaths` reference.
- :func:`build_run_registry` — convenience constructor used by the
  FastAPI dependency in :mod:`server.dependencies`.

How the rest of the system uses this module
-------------------------------------------

- :class:`server.services.run_dispatcher.RunDispatcher` calls
  :meth:`RunRegistry.create` when enqueuing a new run and when
  re-enqueuing a resume.
- :mod:`server.workers.signals` calls :meth:`RunRegistry.mark_running`,
  :meth:`RunRegistry.mark_succeeded`, and
  :meth:`RunRegistry.mark_failed` from the corresponding Celery
  signals.
- :mod:`server.routes.flow` calls :meth:`RunRegistry.get` from the
  ``GET /api/flow/status/{run_id}`` handler.

Invariants enforced by this module
----------------------------------

- Status values are always members of
  :class:`server.schemas.run.RunStatus`.
- :meth:`mark_succeeded`, :meth:`mark_failed`, and
  :meth:`mark_cancelled` apply a TTL equal to
  :attr:`server.settings.ServerSettings.celery_result_expires`.
  Non-terminal transitions leave the TTL untouched.
- The on-disk ``completed_entities.json`` is the source of truth for
  :attr:`server.schemas.run.RunStatusDTO.completed_entity_count`;
  Redis does not mirror the count.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

import redis

from server.redis_client import build_redis_client
from server.schemas.run import RunListItem, RunStatus, RunStatusDTO
from server.settings import ServerSettings, app_redis_url
from server.storage.paths import ServerPaths
from server.storage.run_paths import RunPaths


_STATUS_FIELD: str = "status"
_STARTED_AT_FIELD: str = "started_at"
_FINISHED_AT_FIELD: str = "finished_at"
_ERROR_FIELD: str = "error"
_TOTAL_ROW_COUNT_FIELD: str = "total_row_count"


def _now_iso() -> str:
    """Return the current UTC timestamp as an ISO-8601 string.

    Returns:
        str: ISO-8601 timestamp with ``+00:00`` offset.
    """
    return datetime.now(tz=timezone.utc).isoformat()


class RunRegistry:
    """Redis-hash-backed run status store.

    Attributes:
        paths (ServerPaths): On-disk layout; used to locate
            ``completed_entities.json`` when assembling a
            :class:`server.schemas.run.RunStatusDTO`.
        redis_client (redis.Redis): Connection bound to the application
            Redis DB.
        key_prefix (str): Prefix applied to every hash key.
        terminal_ttl_seconds (int): TTL applied on
            :meth:`mark_succeeded`, :meth:`mark_failed`, and
            :meth:`mark_cancelled`.

    Methods:
        create: Initialise a fresh hash with status ``queued``.
        mark_running: Transition to ``running`` and stamp ``started_at``.
        mark_succeeded: Transition to ``succeeded``, stamp
            ``finished_at``, and set the terminal TTL.
        mark_failed: Transition to ``failed`` with an error message.
        mark_cancelled: Transition to ``cancelled`` (future work).
        get: Return a :class:`RunStatusDTO` enriched with
            ``completed_entity_count`` read from disk.
    """

    def __init__(
        self,
        paths: ServerPaths,
        redis_client: redis.Redis,
        key_prefix: str,
        terminal_ttl_seconds: int,
    ) -> None:
        """Store the injected paths, Redis client, and TTL.

        Args:
            paths (ServerPaths): On-disk layout.
            redis_client (redis.Redis): Client bound to the application
                Redis DB.
            key_prefix (str): Prefix applied to every hash key.
            terminal_ttl_seconds (int): TTL (seconds) applied on
                terminal transitions.
        """
        self.paths = paths
        self.redis_client = redis_client
        self.key_prefix = key_prefix
        self.terminal_ttl_seconds = terminal_ttl_seconds

    def _key(self, run_id: str) -> str:
        """Return the Redis hash key for ``run_id``.

        Args:
            run_id (str): The run identifier.

        Returns:
            str: ``f"{self.key_prefix}:run:{run_id}"``.
        """
        return f"{self.key_prefix}:run:{run_id}"

    def create(self, run_id: str, total_row_count: int = 0) -> None:
        """Initialise the hash for ``run_id`` with status ``queued``.

        Overwrites any prior terminal state, so calling :meth:`create`
        from a resume path puts the run back into the queued state
        without leaving stale ``finished_at`` or ``error`` fields
        behind.

        Args:
            run_id (str): The run identifier.
            total_row_count (int): Number of input rows the run will
                process. Stored in the hash so the frontend can render
                a deterministic progress bar.

        Returns:
            None.
        """
        key = self._key(run_id)
        mapping = {
            _STATUS_FIELD: RunStatus.QUEUED.value,
            _TOTAL_ROW_COUNT_FIELD: str(total_row_count),
        }
        pipeline = self.redis_client.pipeline()
        pipeline.delete(key)
        pipeline.hset(key, mapping=mapping)
        pipeline.persist(key)
        pipeline.execute()

    def mark_running(self, run_id: str) -> None:
        """Record that ``run_id`` is now executing.

        Args:
            run_id (str): The run identifier.

        Returns:
            None.
        """
        self.redis_client.hset(
            self._key(run_id),
            mapping={
                _STATUS_FIELD: RunStatus.RUNNING.value,
                _STARTED_AT_FIELD: _now_iso(),
            },
        )

    def mark_succeeded(self, run_id: str) -> None:
        """Record that ``run_id`` finished successfully and set the TTL.

        Args:
            run_id (str): The run identifier.

        Returns:
            None.
        """
        self._mark_terminal(run_id, RunStatus.SUCCEEDED, error=None)

    def mark_failed(self, run_id: str, error_message: str) -> None:
        """Record that ``run_id`` raised and store the error message.

        Args:
            run_id (str): The run identifier.
            error_message (str): Short description of the failure.

        Returns:
            None.
        """
        self._mark_terminal(run_id, RunStatus.FAILED, error=error_message)

    def mark_cancelled(self, run_id: str) -> None:
        """Record that ``run_id`` was cancelled.

        Reserved for future cancel-endpoint work; not wired to any
        route in this scaffold.

        Args:
            run_id (str): The run identifier.

        Returns:
            None.
        """
        self._mark_terminal(run_id, RunStatus.CANCELLED, error=None)

    def _mark_terminal(
        self, run_id: str, terminal_status: RunStatus, error: Optional[str]
    ) -> None:
        """Apply a terminal status, stamp ``finished_at``, and set TTL.

        Args:
            run_id (str): The run identifier.
            terminal_status (RunStatus): One of the terminal statuses.
            error (Optional[str]): Error message when
                ``terminal_status`` is :attr:`RunStatus.FAILED`; ``None``
                otherwise.

        Returns:
            None.
        """
        key = self._key(run_id)
        mapping = {
            _STATUS_FIELD: terminal_status.value,
            _FINISHED_AT_FIELD: _now_iso(),
        }
        if error is not None:
            mapping[_ERROR_FIELD] = error
        pipeline = self.redis_client.pipeline()
        pipeline.hset(key, mapping=mapping)
        pipeline.expire(key, self.terminal_ttl_seconds)
        pipeline.execute()

    def get(self, run_id: str) -> RunStatusDTO:
        """Return a :class:`RunStatusDTO` for ``run_id``.

        Reads the hash from Redis and enriches it with the
        ``completed_entity_count`` read from
        :attr:`server.storage.run_paths.RunPaths.completed_entities_path`.

        Args:
            run_id (str): The run identifier.

        Returns:
            RunStatusDTO: The current status.

        Raises:
            FileNotFoundError: If no hash exists for ``run_id``.
        """
        key = self._key(run_id)
        raw_hash = self.redis_client.hgetall(key)
        if not raw_hash:
            raise FileNotFoundError(f"Run not found: {run_id}")
        run_paths = RunPaths.for_run_id(self.paths, run_id)
        raw_total = raw_hash.get(_TOTAL_ROW_COUNT_FIELD)
        try:
            total_row_count = int(raw_total) if raw_total else 0
        except (TypeError, ValueError):
            total_row_count = 0
        return RunStatusDTO(
            run_id=run_id,
            status=RunStatus(raw_hash.get(_STATUS_FIELD, RunStatus.QUEUED.value)),
            started_at=raw_hash.get(_STARTED_AT_FIELD) or None,
            finished_at=raw_hash.get(_FINISHED_AT_FIELD) or None,
            error=raw_hash.get(_ERROR_FIELD) or None,
            completed_entity_count=_count_completed_entities(run_paths),
            total_row_count=total_row_count,
        )


    def list_all(self) -> list[RunListItem]:
        """Return a list of all known runs from Redis.

        Scans for all keys matching the run hash pattern and returns
        a :class:`RunListItem` for each. Results are sorted by
        ``started_at`` descending (most recent first); runs without
        a ``started_at`` appear last.

        Returns:
            list[RunListItem]: All runs currently in the registry.
        """
        pattern = f"{self.key_prefix}:run:*"
        items: list[RunListItem] = []
        cursor: int = 0
        while True:
            cursor, keys = self.redis_client.scan(
                cursor=cursor, match=pattern, count=200
            )
            for key in keys:
                raw_hash = self.redis_client.hgetall(key)
                if not raw_hash:
                    continue
                run_id = key.removeprefix(f"{self.key_prefix}:run:")
                flow_name = self._read_flow_name(run_id)
                items.append(
                    RunListItem(
                        run_id=run_id,
                        status=RunStatus(
                            raw_hash.get(_STATUS_FIELD, RunStatus.QUEUED.value)
                        ),
                        started_at=raw_hash.get(_STARTED_AT_FIELD) or None,
                        finished_at=raw_hash.get(_FINISHED_AT_FIELD) or None,
                        flow_name=flow_name,
                    )
                )
            if cursor == 0:
                break
        items.sort(
            key=lambda item: item.started_at or "",
            reverse=True,
        )
        return items

    def _read_flow_name(self, run_id: str) -> Optional[str]:
        """Attempt to read the flow name from the run's flow YAML.

        Args:
            run_id (str): The run identifier.

        Returns:
            Optional[str]: The flow name if found, ``None`` otherwise.
        """
        import yaml as _yaml

        run_paths = RunPaths.for_run_id(self.paths, run_id)
        try:
            with run_paths.flow_yaml_path.open("r", encoding="utf-8") as fh:
                doc = _yaml.safe_load(fh)
        except (OSError, _yaml.YAMLError):
            return None
        if not isinstance(doc, dict):
            return None
        flow_block = doc.get("flow")
        if isinstance(flow_block, dict):
            name = flow_block.get("name")
            if isinstance(name, str) and name:
                return name
            settings = flow_block.get("settings")
            if isinstance(settings, dict):
                name = settings.get("name")
                if isinstance(name, str) and name:
                    return name
        return None


def _count_completed_entities(run_paths: RunPaths) -> int:
    """Return the number of entities listed in the run's checkpoint file.

    Args:
        run_paths (RunPaths): The run's on-disk layout.

    Returns:
        int: Count of entity ids in ``completed_entities.json``; ``0``
        when the file does not yet exist or is malformed.
    """
    completed_path = run_paths.completed_entities_path
    if not completed_path.exists():
        return 0
    try:
        with completed_path.open("r", encoding="utf-8") as file_handle:
            document = json.load(file_handle)
    except (OSError, json.JSONDecodeError):
        return 0
    completed = document.get("completed", []) if isinstance(document, dict) else []
    if not isinstance(completed, list):
        return 0
    return len(completed)


def build_run_registry(
    paths: ServerPaths, settings: ServerSettings
) -> RunRegistry:
    """Construct a :class:`RunRegistry` from settings and paths.

    Args:
        paths (ServerPaths): On-disk layout.
        settings (ServerSettings): Process settings.

    Returns:
        RunRegistry: Service ready to read and write status hashes on
        the application Redis DB.
    """
    redis_client = build_redis_client(settings.redis_url, settings.redis_app_db)
    # ``app_redis_url`` is only used for log/debug contexts; the client
    # construction itself already routes to ``redis_app_db``. Keeping
    # the helper call documented for parity with broker/result URLs.
    _unused_app_url = app_redis_url(settings)
    return RunRegistry(
        paths=paths,
        redis_client=redis_client,
        key_prefix=settings.redis_key_prefix,
        terminal_ttl_seconds=settings.celery_result_expires,
    )
