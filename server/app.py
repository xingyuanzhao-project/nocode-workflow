"""FastAPI application factory for the academic_pipeline web process.

Wires :class:`server.settings.ServerSettings` into
:class:`server.storage.paths.ServerPaths`, constructs every service
singleton once, stashes them on ``app.state``, installs CORS and
exception handlers, mounts every :mod:`server.routes` router, and
returns the configured :class:`fastapi.FastAPI` instance.

On first run, :func:`_seed_presets` copies shipped preset workflows,
codebooks, and data into the runtime directories so they appear as
regular user-owned items.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

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
from server.routes import codebook as codebook_routes
from server.routes import workflows as workflows_routes
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
from server.services.codebook_repository import CodebookRepository
from server.services.workflow_repository import (
    DEFAULT_WORKFLOWS_SOURCE_DIR,
    WorkflowRepository,
)
from server.settings import get_settings
from server.storage.paths import ServerPaths


_log = logging.getLogger(__name__)

_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

WORKFLOWS_SOURCE_DIR: Path = _PROJECT_ROOT / "workflows"
CODEBOOKS_SOURCE_DIR: Path = _PROJECT_ROOT / "codebooks"
DATA_SOURCE_DIR: Path = _PROJECT_ROOT / "data"


def _seed_presets(paths: ServerPaths) -> None:
    """Copy shipped preset workflows, codebooks, and data into runtime dirs.

    Copies only files not already present in the destination, so
    user-modified versions are never overwritten.

    Source directories are fixed relative to the project root:
    - workflows/  -> server/workflows/
    - codebooks/  -> server/codebooks/
    - data/       -> server/data/

    On Render, .dockerignore excludes these source directories from the
    image. glob() returns nothing, so nothing is seeded.  No guards
    needed — the filesystem state IS the decision.
    """
    for workflow_yaml in sorted(WORKFLOWS_SOURCE_DIR.glob("*.yml")):
        destination = paths.workflows_dir / workflow_yaml.name
        if not destination.exists():
            shutil.copy2(workflow_yaml, destination)
            _log.info("Seeded preset workflow: %s", workflow_yaml.name)

    for codebook_json in sorted(CODEBOOKS_SOURCE_DIR.glob("*.json")):
        destination = paths.codebooks_dir / codebook_json.name
        if not destination.exists():
            shutil.copy2(codebook_json, destination)
            _log.info("Seeded preset codebook: %s", codebook_json.name)

    for data_file in sorted(DATA_SOURCE_DIR.glob("*")):
        if data_file.is_file() and data_file.suffix in (".csv", ".json", ".jsonl"):
            destination = paths.data_dir / data_file.name
            if not destination.exists():
                shutil.copy2(data_file, destination)
                _log.info("Seeded preset data file: %s", data_file.name)


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application.

    Returns:
        FastAPI: The wired application instance.
    """
    settings = get_settings()
    configure_logging(settings.log_level)

    paths = ServerPaths.from_settings(settings)

    _seed_presets(paths)

    node_catalog = build_default_node_catalog()
    flow_validator = FlowValidator()
    flow_repository = FlowRepository(paths=paths, validator=flow_validator)
    codebook_repository = CodebookRepository(paths=paths)
    csv_uploader = CSVUploader(paths=paths, settings=settings)
    run_registry = build_run_registry(paths=paths, settings=settings)
    run_dispatcher = RunDispatcher(
        paths=paths,
        registry=run_registry,
        celery_app=celery_app,
        validator=flow_validator,
    )
    results_preview_service = ResultsPreviewService(paths=paths)
    workflow_repository = WorkflowRepository(
        workflows_dir=DEFAULT_WORKFLOWS_SOURCE_DIR,
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
        settings=settings, registry=run_registry, paths=paths
    )

    application = FastAPI(
        title="nocode-workflow backend",
        version="0.1.0",
    )
    application.state.settings = settings
    application.state.paths = paths
    application.state.celery_app = celery_app
    application.state.node_catalog = node_catalog
    application.state.flow_validator = flow_validator
    application.state.flow_repository = flow_repository
    application.state.codebook_repository = codebook_repository
    application.state.csv_uploader = csv_uploader
    application.state.run_registry = run_registry
    application.state.run_dispatcher = run_dispatcher
    application.state.results_preview_service = results_preview_service
    application.state.workflow_repository = workflow_repository
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
    # Register workflow, results, and logs routers BEFORE flow_routes so
    # the ``/api/flow/workflows`` and ``/api/flow/runs/...`` paths are
    # matched literally instead of falling through to
    # ``GET /api/flow/{flow_id}`` with ``flow_id='workflows'`` or
    # ``flow_id='runs'``.
    application.include_router(workflows_routes.router)
    application.include_router(results_routes.router)
    application.include_router(logs_routes.router)
    application.include_router(flow_routes.router)
    application.include_router(prompts_routes.router)
    application.include_router(models_routes.router)
    application.include_router(codebook_routes.router)
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
