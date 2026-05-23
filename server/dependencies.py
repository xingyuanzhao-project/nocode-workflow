"""FastAPI ``Depends`` providers.

Centralises the wiring between :class:`fastapi.FastAPI` routes and the
service layer so every route handler receives fully-constructed
services by type annotation. Keeping providers in one file avoids
scattering ``Depends`` factories across route modules and makes the
dependency graph easy to read.

Contents and relationships
--------------------------

- Every ``get_*`` function below returns one service instance, usually
  stored on ``app.state`` during :func:`server.app.create_app`.
- Routes declare dependencies via
  ``service: NodeCatalog = Depends(get_node_catalog)``; they never
  construct services themselves.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.app` stashes the service singletons on ``app.state``
  once during startup.
- :mod:`server.routes.*` call the ``get_*`` providers here to receive
  those singletons at request time.

Invariants enforced by this module
----------------------------------

- Every provider reads from ``request.app.state`` so tests can swap
  any service by overriding the corresponding attribute before
  dispatching a request.
- No provider constructs a new service; construction happens once in
  :func:`server.app.create_app`.
"""

from __future__ import annotations

from fastapi import Request

from server.services.csv_uploader import CSVUploader
from server.services.flow_repository import FlowRepository
from server.storage.paths import ServerPaths
from server.services.flow_validation import FlowValidator
from server.services.log_stream import LogStreamService
from server.services.model_list_proxy import ModelListProxy
from server.services.node_catalog import NodeCatalog
from server.services.prompts_repository import PromptsRepository
from server.services.results_preview import ResultsPreviewService
from server.services.run_dispatcher import RunDispatcher
from server.services.run_registry import RunRegistry
from server.services.taxonomy_repository import TaxonomyRepository
from server.services.template_repository import TemplateRepository


def get_node_catalog(request: Request) -> NodeCatalog:
    """Return the process-wide :class:`NodeCatalog` from ``app.state``.

    Args:
        request (Request): The incoming request; used to read
            ``request.app.state``.

    Returns:
        NodeCatalog: The node catalog service.
    """
    return request.app.state.node_catalog


def get_flow_validator(request: Request) -> FlowValidator:
    """Return the process-wide :class:`FlowValidator` from ``app.state``.

    Args:
        request (Request): The incoming request.

    Returns:
        FlowValidator: The flow validator service.
    """
    return request.app.state.flow_validator


def get_flow_repository(request: Request) -> FlowRepository:
    """Return the process-wide :class:`FlowRepository` from ``app.state``.

    Args:
        request (Request): The incoming request.

    Returns:
        FlowRepository: The flow repository service.
    """
    return request.app.state.flow_repository


def get_taxonomy_repository(request: Request) -> TaxonomyRepository:
    """Return the process-wide :class:`TaxonomyRepository` from ``app.state``.

    Args:
        request (Request): The incoming request.

    Returns:
        TaxonomyRepository: The taxonomy repository service.
    """
    return request.app.state.taxonomy_repository


def get_server_paths(request: Request) -> ServerPaths:
    """Return the process-wide :class:`ServerPaths` from ``app.state``.

    Args:
        request (Request): The incoming request.

    Returns:
        ServerPaths: The server paths dataclass.
    """
    return request.app.state.paths


def get_csv_uploader(request: Request) -> CSVUploader:
    """Return the process-wide :class:`CSVUploader` from ``app.state``.

    Args:
        request (Request): The incoming request.

    Returns:
        CSVUploader: The CSV upload service.
    """
    return request.app.state.csv_uploader


def get_run_registry(request: Request) -> RunRegistry:
    """Return the process-wide :class:`RunRegistry` from ``app.state``.

    Args:
        request (Request): The incoming request.

    Returns:
        RunRegistry: The run registry service.
    """
    return request.app.state.run_registry


def get_run_dispatcher(request: Request) -> RunDispatcher:
    """Return the process-wide :class:`RunDispatcher` from ``app.state``.

    Args:
        request (Request): The incoming request.

    Returns:
        RunDispatcher: The run dispatcher service.
    """
    return request.app.state.run_dispatcher


def get_results_preview_service(request: Request) -> ResultsPreviewService:
    """Return the process-wide :class:`ResultsPreviewService` from ``app.state``.

    Args:
        request (Request): The incoming request.

    Returns:
        ResultsPreviewService: The results-preview service.
    """
    return request.app.state.results_preview_service


def get_template_repository(request: Request) -> TemplateRepository:
    """Return the process-wide :class:`TemplateRepository` from ``app.state``.

    Args:
        request (Request): The incoming request.

    Returns:
        TemplateRepository: The preset flow-template repository.
    """
    return request.app.state.template_repository


def get_prompts_repository(request: Request) -> PromptsRepository:
    """Return the process-wide :class:`PromptsRepository` from ``app.state``.

    Args:
        request (Request): The incoming request.

    Returns:
        PromptsRepository: The prompts registry service.
    """
    return request.app.state.prompts_repository


def get_model_list_proxy(request: Request) -> ModelListProxy:
    """Return the process-wide :class:`ModelListProxy` from ``app.state``.

    Args:
        request (Request): The incoming request.

    Returns:
        ModelListProxy: The provider model-list proxy service.
    """
    return request.app.state.model_list_proxy


def get_log_stream_service(request: Request) -> LogStreamService:
    """Return the process-wide :class:`LogStreamService` from ``app.state``.

    Args:
        request (Request): The incoming request.

    Returns:
        LogStreamService: The live run-log SSE service.
    """
    return request.app.state.log_stream_service
