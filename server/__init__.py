"""Phase 2 HTTP + worker backend for the config-driven flow runner.

The ``server`` package wraps :mod:`src.node_registry`, :mod:`src.flow_loader`,
and :mod:`src.flow_builder` behind a FastAPI web process and a Celery worker
process. The two processes share state through Redis (status hashes) and the
filesystem (flow YAMLs, uploaded CSVs, per-run output directories).

Contents and relationships
--------------------------

- Top-level modules (this package) hold app-wide composition primitives:
  :mod:`server.app` builds the FastAPI instance, :mod:`server.celery_app`
  builds the Celery instance, :mod:`server.settings` centralises every
  tunable, :mod:`server.logging_config` installs JSON logging,
  :mod:`server.redis_client` owns the application-owned Redis connection
  pool, :mod:`server.dependencies` declares FastAPI ``Depends`` providers,
  and :mod:`server.errors` installs HTTP exception handlers.
- :mod:`server.storage` resolves filesystem paths and nothing else.
- :mod:`server.schemas` holds HTTP-facing Pydantic DTOs and nothing else.
- :mod:`server.services` holds domain logic, each service wrapping one
  specific ``src/`` abstraction or one on-disk folder.
- :mod:`server.workers` holds Celery task bodies and Celery signal
  handlers; it is never imported by the web process.
- :mod:`server.routes` holds thin HTTP handlers that delegate to services.

How the rest of the system uses this package
--------------------------------------------

- ``uvicorn server.app:create_app --factory`` boots the web process.
- ``celery -A server.celery_app worker --pool=solo`` boots the worker
  process.
- Both processes read the same :class:`server.settings.ServerSettings`
  instance, talk to the same Redis URL on the databases assigned in
  settings, and resolve the same :class:`server.storage.paths.ServerPaths`.

Invariants enforced by this package
-----------------------------------

- One responsibility per folder (see :mod:`server` folder docstrings).
- ``src.*`` is imported only by :mod:`server.services.node_catalog`,
  :mod:`server.services.flow_validation`, and
  :mod:`server.workers.flow_task`. No other server module may import from
  ``src.*`` directly.
- Every per-run filesystem path is resolved through
  :class:`server.storage.run_paths.RunPaths`; no module hard-codes
  ``server/data/runs/<run_id>/...`` paths.
"""
