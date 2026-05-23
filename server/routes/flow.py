"""Routes under ``/api/flow`` — flow CRUD and run lifecycle.

Contents and relationships
--------------------------

- :data:`router` — :class:`fastapi.APIRouter` exposing:

  - ``GET /api/flow/list`` — list saved flows.
  - ``POST /api/flow`` — create a new saved flow.
  - ``GET /api/flow/{flow_id}`` — load a saved flow.
  - ``PUT /api/flow/{flow_id}`` — update a saved flow.
  - ``DELETE /api/flow/{flow_id}`` — delete a saved flow.
  - ``POST /api/flow/{flow_id}/duplicate`` — duplicate a saved flow.
  - ``POST /api/flow/run`` — run an ad-hoc (unsaved) flow.
  - ``POST /api/flow/{flow_id}/run`` — run a saved flow.
  - ``POST /api/flow/resume/{run_id}`` — re-enqueue a previous run.
  - ``GET /api/flow/status/{run_id}`` — poll a run's status.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.app` mounts :data:`router` at the root so paths resolve
  to ``/api/flow/...``.

Invariants enforced by this module
----------------------------------

- The ad-hoc run endpoint and the saved-flow run endpoint are distinct
  to keep the DTO surface free of union types.
- The saved-flow run endpoint loads the flow through
  :class:`server.services.flow_repository.FlowRepository` and then
  delegates to :class:`server.services.run_dispatcher.RunDispatcher.submit`;
  it never bypasses the dispatcher.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, status

from server.dependencies import (
    get_flow_repository,
    get_run_dispatcher,
    get_run_registry,
)
from server.schemas.flow import (
    AdhocFlowRunRequest,
    CostEstimateRequest,
    CostEstimateResponse,
    FlowDuplicateRequest,
    FlowGetResponse,
    FlowListItem,
    FlowSaveRequest,
    FlowSaveResponse,
)
from server.schemas.run import RunStartResponse, RunStatusDTO
from server.services.flow_repository import FlowRepository
from server.services.run_dispatcher import RunDispatcher
from server.services.run_registry import RunRegistry


router = APIRouter(prefix="/api/flow", tags=["flow"])
"""Router exposing flow CRUD and run lifecycle endpoints."""


@router.get("/list", response_model=List[FlowListItem])
def list_flows(
    repository: FlowRepository = Depends(get_flow_repository),
) -> List[FlowListItem]:
    """Return a DTO list of every saved flow.

    Args:
        repository (FlowRepository): Injected flow repository.

    Returns:
        List[FlowListItem]: One entry per saved flow.
    """
    return repository.list()


@router.post("", response_model=FlowSaveResponse, status_code=status.HTTP_201_CREATED)
def create_flow(
    request: FlowSaveRequest,
    repository: FlowRepository = Depends(get_flow_repository),
) -> FlowSaveResponse:
    """Persist a new flow under a fresh identifier.

    Args:
        request (FlowSaveRequest): Name and flow body.
        repository (FlowRepository): Injected flow repository.

    Returns:
        FlowSaveResponse: Assigned id and absolute path.
    """
    return repository.save(request)


@router.get("/{flow_id}", response_model=FlowGetResponse)
def get_flow(
    flow_id: str,
    repository: FlowRepository = Depends(get_flow_repository),
) -> FlowGetResponse:
    """Load one saved flow by id.

    Args:
        flow_id (str): Flow identifier.
        repository (FlowRepository): Injected flow repository.

    Returns:
        FlowGetResponse: The loaded flow.
    """
    return repository.get(flow_id)


@router.put("/{flow_id}", response_model=FlowSaveResponse)
def update_flow(
    flow_id: str,
    request: FlowSaveRequest,
    repository: FlowRepository = Depends(get_flow_repository),
) -> FlowSaveResponse:
    """Overwrite the YAML at ``flow_id``.

    Args:
        flow_id (str): Flow identifier.
        request (FlowSaveRequest): New name and flow body.
        repository (FlowRepository): Injected flow repository.

    Returns:
        FlowSaveResponse: ``flow_id`` echoed back with the path.
    """
    return repository.update(flow_id, request)


@router.delete("/{flow_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_flow(
    flow_id: str,
    repository: FlowRepository = Depends(get_flow_repository),
) -> None:
    """Remove the YAML file for ``flow_id``.

    Args:
        flow_id (str): Flow identifier.
        repository (FlowRepository): Injected flow repository.

    Returns:
        None.
    """
    repository.delete(flow_id)


@router.post(
    "/{flow_id}/duplicate",
    response_model=FlowSaveResponse,
    status_code=status.HTTP_201_CREATED,
)
def duplicate_flow(
    flow_id: str,
    request: FlowDuplicateRequest,
    repository: FlowRepository = Depends(get_flow_repository),
) -> FlowSaveResponse:
    """Copy an existing flow under ``request.new_name``.

    Args:
        flow_id (str): Source flow identifier.
        request (FlowDuplicateRequest): New name for the copy.
        repository (FlowRepository): Injected flow repository.

    Returns:
        FlowSaveResponse: Id and path of the new copy.
    """
    return repository.duplicate(flow_id, request.new_name)


MODEL_COST_PER_MILLION_TOKENS: dict[str, float] = {
    "meta-llama/llama-3.1-70b-instruct": 0.40,
    "meta-llama/llama-3.1-8b-instruct": 0.06,
    "meta-llama/llama-3.3-70b-instruct": 0.30,
    "qwen/qwen-2.5-72b-instruct": 0.36,
    "mistralai/mistral-large-latest": 2.00,
    "google/gemini-2.0-flash-001": 0.10,
    "gpt-4o": 2.50,
    "gpt-4o-mini": 0.15,
    "gpt-4-turbo": 10.00,
    "gpt-3.5-turbo": 0.50,
}
"""Per-million-token costs for common models. Used by the cost estimator
as a lookup table. Models not in this table fall back to a conservative
default of $1.00 / 1M tokens."""

DEFAULT_COST_PER_MILLION_TOKENS: float = 1.00
"""Fallback rate when the model is not in :data:`MODEL_COST_PER_MILLION_TOKENS`."""

CHARS_PER_TOKEN: int = 4
"""Rough heuristic: 1 token ~ 4 characters of English text."""


@router.post("/estimate-cost", response_model=CostEstimateResponse)
def estimate_cost(request: CostEstimateRequest) -> CostEstimateResponse:
    """Return an order-of-magnitude cost estimate for a flow run.

    The estimate uses a chars-to-tokens heuristic and a per-model rate
    lookup table. It is intentionally rough: the purpose is to let the
    user catch accidental large runs before they start, not to produce
    an invoice-grade projection.

    Args:
        request (CostEstimateRequest): Flow definition plus data stats.

    Returns:
        CostEstimateResponse: Estimated tokens, cost, and a summary
        message.
    """
    flow_block = request.flow
    nodes = flow_block.get("nodes", []) or []
    model_name = "unknown"
    step_count = 0
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = node.get("type")
        node_config = node.get("config") or {}
        if not isinstance(node_config, dict):
            node_config = {}
        if node_type == "llm_call" and model_name == "unknown":
            candidate_model = node_config.get("model")
            if isinstance(candidate_model, str) and candidate_model:
                model_name = candidate_model
        elif node_type == "processor":
            step_count += 1

    estimated_input_tokens = request.total_characters // CHARS_PER_TOKEN
    total_tokens = estimated_input_tokens * max(step_count, 1)

    cost_per_million = MODEL_COST_PER_MILLION_TOKENS.get(
        model_name, DEFAULT_COST_PER_MILLION_TOKENS
    )
    estimated_cost = (total_tokens / 1_000_000) * cost_per_million

    message = (
        f"~{total_tokens:,} tokens across {step_count} step(s) on "
        f"{model_name} @ ${cost_per_million:.2f}/1M tokens = "
        f"~${estimated_cost:.4f}"
    )

    return CostEstimateResponse(
        estimated_tokens=total_tokens,
        estimated_cost_usd=round(estimated_cost, 6),
        model=model_name,
        step_count=step_count,
        message=message,
    )


@router.post(
    "/run", response_model=RunStartResponse, status_code=status.HTTP_202_ACCEPTED
)
def run_adhoc_flow(
    request: AdhocFlowRunRequest,
    dispatcher: RunDispatcher = Depends(get_run_dispatcher),
) -> RunStartResponse:
    """Enqueue an ad-hoc (unsaved) flow.

    Args:
        request (AdhocFlowRunRequest): The flow body to run.
        dispatcher (RunDispatcher): Injected run dispatcher.

    Returns:
        RunStartResponse: The new ``run_id`` and initial status.
    """
    return dispatcher.submit(request.flow)


@router.post(
    "/{flow_id}/run",
    response_model=RunStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def run_saved_flow(
    flow_id: str,
    repository: FlowRepository = Depends(get_flow_repository),
    dispatcher: RunDispatcher = Depends(get_run_dispatcher),
) -> RunStartResponse:
    """Enqueue a run of the saved flow identified by ``flow_id``.

    The flow is loaded from disk and passed to the dispatcher's
    :meth:`submit` method; a new ``run_id`` and run directory are
    created. The original saved flow is not mutated.

    Args:
        flow_id (str): Saved flow identifier.
        repository (FlowRepository): Injected flow repository.
        dispatcher (RunDispatcher): Injected run dispatcher.

    Returns:
        RunStartResponse: The new ``run_id`` and initial status.
    """
    saved_flow = repository.get(flow_id)
    return dispatcher.submit(saved_flow.flow)


@router.post(
    "/resume/{run_id}",
    response_model=RunStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def resume_run(
    run_id: str,
    dispatcher: RunDispatcher = Depends(get_run_dispatcher),
) -> RunStartResponse:
    """Re-enqueue an existing run by id.

    The dispatcher does not rewrite the run's flow YAML; the worker
    passes ``resume=True`` to :func:`src.flow_builder.build_flow`, so
    already-completed entities are skipped via the checkpoint file.

    Args:
        run_id (str): Existing run identifier.
        dispatcher (RunDispatcher): Injected run dispatcher.

    Returns:
        RunStartResponse: ``run_id`` echoed back with status ``queued``.
    """
    return dispatcher.resume(run_id)


@router.get("/status/{run_id}", response_model=RunStatusDTO)
def get_run_status(
    run_id: str,
    registry: RunRegistry = Depends(get_run_registry),
) -> RunStatusDTO:
    """Return the current status of ``run_id``.

    Args:
        run_id (str): Run identifier.
        registry (RunRegistry): Injected run registry service.

    Returns:
        RunStatusDTO: Current lifecycle position plus the completed
        entity count from the run's checkpoint file.
    """
    return registry.get(run_id)
