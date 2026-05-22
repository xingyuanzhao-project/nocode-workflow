"""FastAPI application factory for the agent_paper web process.

Wires :class:`server.settings.ServerSettings` into
:class:`server.storage.paths.ServerPaths`, constructs every service
singleton once, stashes them on ``app.state``, installs CORS and
exception handlers, mounts every :mod:`server.routes` router, and
returns the configured :class:`fastapi.FastAPI` instance.

Contents and relationships
--------------------------

- :func:`create_app` — the factory called by
  ``uvicorn server.app:create_app --factory``.

How the rest of the system uses this module
-------------------------------------------

- Uvicorn constructs the app with :func:`create_app`.
- Every HTTP route handler reads its services from ``request.app.state``
  via the providers in :mod:`server.dependencies`.

Invariants enforced by this module
----------------------------------

- Every service is constructed exactly once per process.
- The Celery app shared with :mod:`server.services.run_dispatcher` and
  :mod:`server.routes.health` comes from :data:`server.celery_app.celery_app`,
  not from a fresh :class:`celery.Celery` instance.
- The shared :class:`httpx.AsyncClient` used by
  :class:`server.services.model_list_proxy.ModelListProxy` is closed
  exactly once via an ``on_event("shutdown")`` hook so the process
  does not leak sockets on restart.
- Logging is configured before any other module logs anything from
  :func:`create_app`.
"""

from __future__ import annotations

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.celery_app import celery_app
from server.errors import install_exception_handlers
from server.logging_config import configure_logging
from server.redis_client import build_redis_client
from server.routes import files as files_routes
from server.routes import flow as flow_routes
from server.routes import health as health_routes
from server.routes import logs as logs_routes
from server.routes import models as models_routes
from server.routes import prompts as prompts_routes
from server.routes import results as results_routes
from server.routes import schema as schema_routes
from server.routes import settings as settings_routes
from server.routes import taxonomy as taxonomy_routes
from server.routes import templates as templates_routes
from server.services.csv_uploader import CSVUploader
from server.services.flow_repository import FlowRepository
from server.services.flow_validation import FlowValidator
from server.services.log_stream import build_log_stream_service
from server.services.model_list_proxy import ModelListProxy
from server.services.node_catalog import build_default_node_catalog
from server.services.prompts_repository import PromptsRepository
from server.services.results_preview import ResultsPreviewService
from server.services.run_dispatcher import RunDispatcher
from server.services.run_registry import build_run_registry
from server.services.taxonomy_repository import TaxonomyRepository
from server.services.template_repository import (
    DEFAULT_TEMPLATES_DIR,
    TemplateRepository,
)
from server.settings import get_settings
from server.storage.paths import ServerPaths


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application.

    Returns:
        FastAPI: The wired application instance.
    """
    settings = get_settings()
    configure_logging(settings.log_level)

    paths = ServerPaths.from_settings(settings)

    node_catalog = build_default_node_catalog()
    flow_validator = FlowValidator()
    flow_repository = FlowRepository(paths=paths, validator=flow_validator)
    taxonomy_repository = TaxonomyRepository(paths=paths)
    csv_uploader = CSVUploader(paths=paths, settings=settings)
    run_registry = build_run_registry(paths=paths, settings=settings)
    run_dispatcher = RunDispatcher(
        paths=paths,
        registry=run_registry,
        celery_app=celery_app,
        validator=flow_validator,
    )
    results_preview_service = ResultsPreviewService(paths=paths)
    template_repository = TemplateRepository(
        templates_dir=DEFAULT_TEMPLATES_DIR,
        validator=flow_validator,
    )
    prompts_repository = PromptsRepository()
    app_redis_client = build_redis_client(settings.redis_url, settings.redis_app_db)
    upstream_http_client = httpx.AsyncClient()
    model_list_proxy = ModelListProxy(
        redis_client=app_redis_client,
        http_client=upstream_http_client,
        key_prefix=settings.redis_key_prefix,
    )
    log_stream_service = build_log_stream_service(
        settings=settings, registry=run_registry
    )

    application = FastAPI(
        title="agent_paper backend",
        version="0.1.0",
    )
    application.state.settings = settings
    application.state.paths = paths
    application.state.celery_app = celery_app
    application.state.node_catalog = node_catalog
    application.state.flow_validator = flow_validator
    application.state.flow_repository = flow_repository
    application.state.taxonomy_repository = taxonomy_repository
    application.state.csv_uploader = csv_uploader
    application.state.run_registry = run_registry
    application.state.run_dispatcher = run_dispatcher
    application.state.results_preview_service = results_preview_service
    application.state.template_repository = template_repository
    application.state.prompts_repository = prompts_repository
    application.state.model_list_proxy = model_list_proxy
    application.state.upstream_http_client = upstream_http_client
    application.state.log_stream_service = log_stream_service

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    install_exception_handlers(application)

    application.include_router(schema_routes.router)
    # Register template, results, and logs routers BEFORE flow_routes so
    # the ``/api/flow/templates`` and ``/api/flow/runs/...`` paths are
    # matched literally instead of falling through to
    # ``GET /api/flow/{flow_id}`` with ``flow_id='templates'`` or
    # ``flow_id='runs'``.
    application.include_router(templates_routes.router)
    application.include_router(results_routes.router)
    application.include_router(logs_routes.router)
    application.include_router(flow_routes.router)
    application.include_router(prompts_routes.router)
    application.include_router(models_routes.router)
    application.include_router(taxonomy_routes.router)
    application.include_router(files_routes.router)
    application.include_router(settings_routes.router)
    application.include_router(health_routes.router)

    @application.on_event("shutdown")
    async def _close_upstream_http_client() -> None:
        """Close the long-lived :class:`httpx.AsyncClient` on shutdown.

        Uvicorn calls this once per process when SIGTERM / SIGINT
        arrives, releasing the httpx connection pool cleanly.
        """
        await upstream_http_client.aclose()

    return application
