"""HTTP DTOs for the flow validation, CRUD, and run endpoints.

The flow body itself stays as a raw :class:`dict` at the HTTP layer; the
service layer hands it to :class:`src.flow_loader.FlowSchema.model_validate`
which owns the real schema. That split keeps the server schemas
thin and lets the flow schema evolve without rippling into this module.

Contents and relationships
--------------------------

- :class:`FlowValidationRequest` / :class:`FlowValidationResponse` —
  payload and response for ``POST /api/schema/validate``.
- :class:`FlowSaveRequest` / :class:`FlowSaveResponse` — payload and
  response for ``POST /api/flow`` and ``PUT /api/flow/{id}``.
- :class:`FlowListItem` — per-entry shape returned by
  ``GET /api/flow/list``.
- :class:`AdhocFlowRunRequest` — body for ``POST /api/flow/run``
  carrying an unsaved flow.
- The saved-flow run endpoint (``POST /api/flow/{id}/run``) takes no
  body; the flow identifier is in the path.

How the rest of the system uses this module
-------------------------------------------

- :class:`server.services.flow_validation.FlowValidator` consumes
  :attr:`FlowValidationRequest.flow` and returns
  :class:`FlowValidationResponse`.
- :class:`server.services.flow_repository.FlowRepository` consumes
  :class:`FlowSaveRequest` and produces :class:`FlowSaveResponse` and
  :class:`FlowListItem`.
- :class:`server.services.run_dispatcher.RunDispatcher` consumes the
  raw flow dict carried by :attr:`AdhocFlowRunRequest.flow`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from server.schemas.errors import ValidationErrorItem


class FlowValidationRequest(BaseModel):
    """Body of ``POST /api/schema/validate``.

    Attributes:
        flow (Dict[str, Any]): Raw flow definition as it appears under
            the ``flow:`` key of a flow YAML. Validated by
            :class:`server.services.flow_validation.FlowValidator`.
    """

    model_config = ConfigDict(extra="forbid")

    flow: Dict[str, Any]


class FlowValidationResponse(BaseModel):
    """Response of ``POST /api/schema/validate``.

    Attributes:
        valid (bool): ``True`` iff :attr:`errors` is empty.
        errors (List[ValidationErrorItem]): One entry per schema
            violation; empty when :attr:`valid` is ``True``.
    """

    model_config = ConfigDict(extra="forbid")

    valid: bool
    errors: List[ValidationErrorItem] = Field(default_factory=list)


class FlowSaveRequest(BaseModel):
    """Body of ``POST /api/flow`` and ``PUT /api/flow/{id}``.

    Attributes:
        name (str): Human-readable flow name. Also used as the seed for
            the derived ``flow_id`` slug on create.
        flow (Dict[str, Any]): Raw flow definition; validated before
            being written to disk.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    flow: Dict[str, Any]


class FlowSaveResponse(BaseModel):
    """Response of ``POST /api/flow`` and ``PUT /api/flow/{id}``.

    Attributes:
        id (str): Identifier assigned by
            :class:`server.services.flow_repository.FlowRepository`.
        path (str): Absolute on-disk path of the saved YAML.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    path: str


class FlowListItem(BaseModel):
    """One entry in the response of ``GET /api/flow/list``.

    Attributes:
        id (str): Flow identifier.
        name (str): Human-readable flow name.
        description (str): Free-form description copied from
            ``flow.description`` when present.
        updated_at (str): ISO-8601 timestamp of the YAML's last
            modification.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str = ""
    updated_at: str


class FlowDuplicateRequest(BaseModel):
    """Body of ``POST /api/flow/{id}/duplicate``.

    Attributes:
        new_name (str): Name assigned to the new copy.
    """

    model_config = ConfigDict(extra="forbid")

    new_name: str


class AdhocFlowRunRequest(BaseModel):
    """Body of ``POST /api/flow/run``.

    The saved-flow run endpoint (``POST /api/flow/{id}/run``) takes no
    body; only the ad-hoc endpoint uses this DTO. Keeping the two
    endpoints distinct avoids a union-typed "one of flow or flow_id"
    request that would need a discriminator validator.

    Attributes:
        flow (Dict[str, Any]): Raw, unsaved flow definition to run.
    """

    model_config = ConfigDict(extra="forbid")

    flow: Dict[str, Any]


class FlowGetResponse(BaseModel):
    """Response of ``GET /api/flow/{id}``.

    Attributes:
        id (str): Flow identifier.
        name (str): Human-readable flow name.
        flow (Dict[str, Any]): Raw flow definition loaded from disk.
        updated_at (str): ISO-8601 timestamp of the YAML's last
            modification.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    flow: Dict[str, Any]
    updated_at: str


class CostEstimateRequest(BaseModel):
    """Body of ``POST /api/flow/estimate-cost``.

    Attributes:
        flow (Dict[str, Any]): Raw flow definition — the estimator
            reads model, provider, ``max_tokens``, edges, and
            ``settings.processing_limit`` from the flow body.
        row_count (int): Fallback number of input rows when
            ``settings.processing_limit`` is not set on the flow.
        total_characters (int): Kept for wire compatibility; no longer
            used by the estimator (tokens are derived from
            ``max_tokens`` instead).
    """

    model_config = ConfigDict(extra="forbid")

    flow: Dict[str, Any]
    row_count: int
    total_characters: int


class CostEstimateResponse(BaseModel):
    """Response of ``POST /api/flow/estimate-cost``.

    Attributes:
        model (str): Model name used for the estimate.
        provider (str): Provider name (``openrouter``, ``google``, etc.).
        is_local (bool): ``True`` when the provider is a local server
            (ollama / vllm / llama_cpp) — price is always zero.
        model_price_per_million_tokens (float): Output-token cost in
            USD per 1 M tokens, sourced from the provider's cached
            pricing or a static fallback table.
        api_calls (int): Estimated total LLM API calls
            (``row_count * llm_edges``).
        max_tokens_per_call (int): ``max_tokens`` budget configured on
            the LLM Call node.
        estimated_tokens (int): ``api_calls * max_tokens_per_call``.
        estimated_cost_usd (float): Order-of-magnitude cost in USD.
        message (str): Human-readable summary of the estimate.
    """

    model_config = ConfigDict(extra="forbid")

    model: str
    provider: str
    is_local: bool
    model_price_per_million_tokens: float
    api_calls: int
    max_tokens_per_call: int
    estimated_tokens: int
    estimated_cost_usd: float
    message: str


__all__ = [
    "AdhocFlowRunRequest",
    "CostEstimateRequest",
    "CostEstimateResponse",
    "FlowDuplicateRequest",
    "FlowGetResponse",
    "FlowListItem",
    "FlowSaveRequest",
    "FlowSaveResponse",
    "FlowValidationRequest",
    "FlowValidationResponse",
]
