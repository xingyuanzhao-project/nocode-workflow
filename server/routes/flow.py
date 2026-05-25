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

import logging
from typing import List

from fastapi import APIRouter, Depends, status

from server.dependencies import (
    get_flow_repository,
    get_model_list_proxy,
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
from server.schemas.models import ProviderModelsResponse
from server.schemas.run import RunListItem, RunStartResponse, RunStatusDTO
from server.services.flow_repository import FlowRepository
from server.services.model_list_proxy import ModelListProxy
from server.services.run_dispatcher import RunDispatcher
from server.services.run_registry import RunRegistry


_log = logging.getLogger(__name__)

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


@router.get("/runs", response_model=List[RunListItem])
def list_runs(
    registry: RunRegistry = Depends(get_run_registry),
) -> List[RunListItem]:
    """Return a list of all known runs, most recent first.

    Returns an empty list when no runs exist or when the registry
    is temporarily unavailable (e.g. Redis not yet populated).

    Args:
        registry (RunRegistry): Injected run registry service.

    Returns:
        List[RunListItem]: Every run currently tracked in the registry.
    """
    try:
        return registry.list_all()
    except FileNotFoundError:
        _log.debug("No runs found in registry, returning empty list")
        return []


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


LOCAL_PROVIDERS: frozenset[str] = frozenset({"ollama", "vllm", "llama_cpp"})

# Output-token price per 1 M tokens (USD).  Sourced from official
# pricing pages as of May 2026.  The estimate endpoint prefers the
# live pricing cached from the OpenRouter catalogue; this table is
# the fallback when the cache has no entry for the model.
#
# Sources:
#   Google  – https://ai.google.dev/gemini-api/docs/pricing
#   OpenAI  – https://platform.openai.com/docs/pricing
#   Anthropic – https://docs.anthropic.com/en/docs/about-claude/pricing
#   OpenRouter – https://openrouter.ai/models (pass-through pricing)
MODEL_OUTPUT_PRICE_PER_MILLION: dict[str, float] = {
    # Google (via OpenRouter)
    "google/gemini-2.5-flash": 2.50,
    "google/gemini-2.5-pro": 10.00,
    "google/gemini-2.0-flash-001": 0.40,
    "google/gemini-2.0-flash": 0.40,
    # Google (direct)
    "gemini-2.5-flash": 2.50,
    "gemini-2.5-pro": 10.00,
    "gemini-2.0-flash-001": 0.40,
    # OpenAI (direct and via OpenRouter)
    "gpt-4.1": 8.00,
    "gpt-4.1-mini": 1.60,
    "gpt-4.1-nano": 0.40,
    "gpt-4o": 10.00,
    "gpt-4o-mini": 0.60,
    "openai/gpt-4o": 10.00,
    "openai/gpt-4o-mini": 0.60,
    "openai/gpt-4.1": 8.00,
    "openai/gpt-4.1-mini": 1.60,
    "openai/gpt-4.1-nano": 0.40,
    # Anthropic
    "claude-3.5-haiku": 4.00,
    "claude-sonnet-4": 15.00,
    "claude-opus-4": 75.00,
    "anthropic/claude-3.5-haiku": 4.00,
    "anthropic/claude-sonnet-4": 15.00,
    "anthropic/claude-opus-4": 75.00,
    # Meta Llama (OpenRouter)
    "meta-llama/llama-3.3-70b-instruct": 0.30,
    "meta-llama/llama-3.1-70b-instruct": 0.40,
    "meta-llama/llama-3.1-8b-instruct": 0.06,
    # Mistral
    "mistralai/mistral-large-latest": 6.00,
    "mistralai/mistral-small": 0.30,
}

DEFAULT_OUTPUT_PRICE_PER_MILLION: float = 1.00
"""Fallback output-token rate when neither the cache nor the static
table contains a match."""


def _lookup_cached_pricing(
    model_proxy: ModelListProxy,
    provider: str,
    model_name: str,
) -> float | None:
    """Try to read the output-token price from the Redis model cache.

    Returns the completion price per 1 M tokens, or ``None`` on miss.
    """
    cache_key = f"{model_proxy.key_prefix}:models:{provider}"
    try:
        raw = model_proxy.redis_client.get(cache_key)
    except Exception:
        return None
    if raw is None:
        return None
    try:
        cached = ProviderModelsResponse.model_validate_json(raw)
    except Exception:
        return None
    for entry in cached.models:
        if entry.id == model_name and entry.completion_price_per_million is not None:
            return entry.completion_price_per_million
    return None


def _resolve_output_price(
    model_proxy: ModelListProxy,
    provider: str,
    model_name: str,
) -> float:
    """Return the output price per 1 M tokens for *model_name*.

    Resolution order:
    1. Provider is local → 0.
    2. Cached OpenRouter catalogue entry → live price.
    3. Static :data:`MODEL_OUTPUT_PRICE_PER_MILLION` table.
    4. :data:`DEFAULT_OUTPUT_PRICE_PER_MILLION`.
    """
    if provider in LOCAL_PROVIDERS:
        return 0.0
    cached = _lookup_cached_pricing(model_proxy, provider, model_name)
    if cached is not None:
        return cached
    return MODEL_OUTPUT_PRICE_PER_MILLION.get(
        model_name, DEFAULT_OUTPUT_PRICE_PER_MILLION
    )


@router.post("/estimate-cost", response_model=CostEstimateResponse)
def estimate_cost(
    request: CostEstimateRequest,
    model_proxy: ModelListProxy = Depends(get_model_list_proxy),
) -> CostEstimateResponse:
    """Return an order-of-magnitude cost estimate for a flow run.

    The estimate is based on the ``max_tokens`` budget from the LLM
    Call node multiplied by the number of API calls (rows times the
    number of LLM-using processors).  Pricing is looked up from the
    cached provider catalogue when available, falling back to a static
    table sourced from official pricing pages.

    Args:
        request (CostEstimateRequest): Flow definition plus row count.
        model_proxy (ModelListProxy): Injected model-list proxy (used
            to read cached pricing from Redis).

    Returns:
        CostEstimateResponse: Estimated tokens, cost, and a summary.
    """
    flow_block = request.flow
    nodes = flow_block.get("nodes", []) or []
    edges = flow_block.get("edges", []) or []
    settings = flow_block.get("settings") or {}

    model_name = "unknown"
    provider = "unknown"
    max_tokens = 1024

    for node in nodes:
        if not isinstance(node, dict):
            continue
        if node.get("type") != "llm_call":
            continue
        node_config = node.get("config") or {}
        if not isinstance(node_config, dict):
            node_config = {}
        candidate_model = node_config.get("model")
        if isinstance(candidate_model, str) and candidate_model and model_name == "unknown":
            model_name = candidate_model
            provider = str(node_config.get("provider", "unknown"))
            raw_max = node_config.get("max_tokens")
            if isinstance(raw_max, (int, float)) and raw_max > 0:
                max_tokens = int(raw_max)

    llm_edges = sum(
        1
        for e in edges
        if isinstance(e, dict) and e.get("type") == "llm_call"
    )

    processing_limit = None
    if isinstance(settings, dict):
        raw_limit = settings.get("processing_limit")
        if isinstance(raw_limit, (int, float)) and raw_limit > 0:
            processing_limit = int(raw_limit)

    row_count = processing_limit if processing_limit is not None else request.row_count
    api_calls = row_count * max(llm_edges, 1)

    is_local = provider in LOCAL_PROVIDERS
    output_price = _resolve_output_price(model_proxy, provider, model_name)

    estimated_tokens = api_calls * max_tokens
    estimated_cost = (estimated_tokens / 1_000_000) * output_price

    if is_local:
        price_label = "free (local)"
    else:
        price_label = f"${output_price:.2f}/1M tokens"

    message = (
        f"{api_calls:,} API calls × {max_tokens:,} max_tokens = "
        f"~{estimated_tokens:,} tokens on {model_name} @ {price_label}"
        f" = ~${estimated_cost:.4f}"
    )

    return CostEstimateResponse(
        model=model_name,
        provider=provider,
        is_local=is_local,
        model_price_per_million_tokens=output_price,
        api_calls=api_calls,
        max_tokens_per_call=max_tokens,
        estimated_tokens=estimated_tokens,
        estimated_cost_usd=round(estimated_cost, 6),
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
    """Return the current status of ``run_id`` from the Redis registry.

    Args:
        run_id (str): Run identifier.
        registry (RunRegistry): Injected run registry service.

    Returns:
        RunStatusDTO: Current lifecycle position plus the completed
        entity count from the run's checkpoint file.
    """
    return registry.get(run_id)
