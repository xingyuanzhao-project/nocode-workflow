"""Centralised configuration for the server package.

Every tunable read by :mod:`server.app`, :mod:`server.celery_app`, the
workers, and the services lives on :class:`ServerSettings`. Settings are
populated from environment variables prefixed with ``ACADEMIC_PIPELINE_`` (for
example ``ACADEMIC_PIPELINE_REDIS_URL``) so production deployment reduces to a
managed Redis URL and a data directory.

Contents and relationships
--------------------------

- :class:`ServerSettings` — the single :class:`pydantic_settings.BaseSettings`
  instance that holds every knob. Exposes paths
  (:attr:`ServerSettings.data_dir`), CORS origins
  (:attr:`ServerSettings.cors_origins`), Redis coordinates
  (:attr:`ServerSettings.redis_url`, :attr:`ServerSettings.redis_broker_db`,
  :attr:`ServerSettings.redis_result_db`,
  :attr:`ServerSettings.redis_app_db`,
  :attr:`ServerSettings.redis_key_prefix`), upload limits
  (:attr:`ServerSettings.max_upload_bytes`), Celery tunables
  (:attr:`ServerSettings.celery_result_expires`,
  :attr:`ServerSettings.worker_shutdown_timeout`), and logging
  (:attr:`ServerSettings.log_level`).
- :func:`get_settings` — LRU-cached factory used by FastAPI dependencies
  and by the Celery app factory so both processes agree on one instance.
- :func:`broker_url` / :func:`result_backend_url` — derive the Celery
  broker and result-backend URLs from :attr:`ServerSettings.redis_url`
  and the DB ints, so there is exactly one place that knows how to
  construct them.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.app`'s ``create_app`` calls :func:`get_settings` once to
  feed :class:`server.storage.paths.ServerPaths` and construct the
  singletons installed on the app state.
- :mod:`server.celery_app` reads :func:`broker_url` and
  :func:`result_backend_url` plus the ``celery_*`` fields to build the
  Celery instance.
- :mod:`server.redis_client` reads :attr:`ServerSettings.redis_url` and a
  caller-specified DB int to build an application-owned Redis client.

Invariants enforced by this module
----------------------------------

- Broker, result backend, and application state each get a distinct Redis
  logical DB, so Celery's managed keys never collide with
  application-owned keys.
- Every URL construction goes through :func:`broker_url` or
  :func:`result_backend_url`; call sites never hand-assemble URLs.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
"""Repository root, the parent of the ``server`` package directory."""


class ServerSettings(BaseSettings):
    """Process-wide configuration for the web and worker processes.

    Attributes:
        server_root (Path): Base directory for runtime subdirectories
            ``workflows/``, ``codebooks/``, ``data/``, and ``runs/``.
            Defaults to ``<project_root>/server``.
        cors_origins (List[str]): Origins allowed by
            :class:`fastapi.middleware.cors.CORSMiddleware`.
        redis_url (str): Base Redis URL without a database suffix. For
            example ``redis://localhost:6379``. The DB suffix is added
            by :func:`broker_url`, :func:`result_backend_url`, and the
            application client based on the ``redis_*_db`` ints below.
        redis_broker_db (int): Redis logical DB index used by the Celery
            broker. Default ``0``.
        redis_result_db (int): Redis logical DB index used by the Celery
            result backend. Default ``1``.
        redis_app_db (int): Redis logical DB index used by the
            application (:mod:`server.services.run_registry`). Default
            ``2``.
        redis_key_prefix (str): Prefix applied to every application-owned
            Redis key (for example ``academic_pipeline:run:<run_id>``) so the
            DB namespace stays human-readable.
        max_upload_bytes (int): Upper bound on the size of an uploaded
            CSV, enforced by :class:`server.services.csv_uploader.CSVUploader`.
        celery_result_expires (int): TTL in seconds applied to entries
            in the Celery result backend *and* to terminal entries in
            :class:`server.services.run_registry.RunRegistry` so both
            GC on the same cadence. Default ``86400`` (one day).
        worker_shutdown_timeout (int): Grace period in seconds the
            Celery worker waits for in-flight tasks to finish when it
            receives SIGTERM. Default ``60``. Long-running tasks rely on
            ``task_acks_late`` to survive abrupt shutdowns; this timeout
            bounds the graceful path.
        log_level (str): Root logger level applied by
            :func:`server.logging_config.configure_logging`. Default
            ``"INFO"``.

    Methods:
        (none; configuration is read-only)
    """

    model_config = SettingsConfigDict(
        env_prefix="ACADEMIC_PIPELINE_",
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    server_root: Path = Field(default=_PROJECT_ROOT / "server")
    cors_origins: List[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    redis_url: str = "redis://localhost:6379"
    redis_broker_db: int = 0
    redis_result_db: int = 1
    redis_app_db: int = 2
    redis_key_prefix: str = "academic_pipeline"

    max_upload_bytes: int = 500 * 1024 * 1024

    celery_result_expires: int = 86_400
    worker_shutdown_timeout: int = 60

    log_level: str = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> ServerSettings:
    """Return the process-wide cached :class:`ServerSettings` instance.

    The first call reads environment variables and the repository-root
    ``.env`` file; subsequent calls return the same object. Tests can
    clear the cache with ``get_settings.cache_clear()``.

    Returns:
        ServerSettings: The cached settings instance.
    """
    return ServerSettings()


def broker_url(settings: ServerSettings) -> str:
    """Return the Celery broker URL derived from ``settings``.

    Args:
        settings (ServerSettings): The settings instance.

    Returns:
        str: ``"<redis_url>/<redis_broker_db>"``.
    """
    return f"{settings.redis_url.rstrip('/')}/{settings.redis_broker_db}"


def result_backend_url(settings: ServerSettings) -> str:
    """Return the Celery result-backend URL derived from ``settings``.

    Args:
        settings (ServerSettings): The settings instance.

    Returns:
        str: ``"<redis_url>/<redis_result_db>"``.
    """
    return f"{settings.redis_url.rstrip('/')}/{settings.redis_result_db}"


def app_redis_url(settings: ServerSettings) -> str:
    """Return the application-owned Redis URL derived from ``settings``.

    Used by :mod:`server.redis_client` to build the connection pool that
    backs :class:`server.services.run_registry.RunRegistry` and the
    health-check ping.

    Args:
        settings (ServerSettings): The settings instance.

    Returns:
        str: ``"<redis_url>/<redis_app_db>"``.
    """
    return f"{settings.redis_url.rstrip('/')}/{settings.redis_app_db}"
