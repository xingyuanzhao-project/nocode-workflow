"""HTTP DTOs for the workflow endpoints.

The GUI shows a "New Flow" dialog with a short list of preset workflows,
and then loads the chosen workflow onto the canvas. Two DTOs cover
those two steps:

- :class:`WorkflowListItem` — compact list-view entry (no flow body).
- :class:`WorkflowDetail` — full detail view including the raw flow
  body the GUI rehydrates into canvas nodes.

Contents and relationships
--------------------------

- :class:`WorkflowListItem` — returned by
  :class:`server.services.workflow_repository.WorkflowRepository.list`.
- :class:`WorkflowDetail` — returned by
  :meth:`WorkflowRepository.get`.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.routes.workflows` consumes both DTOs and exposes them
  over HTTP.
- The GUI's ``NewFlowDialog`` component reads
  :class:`WorkflowListItem` from ``GET /api/flow/workflows`` and
  :class:`WorkflowDetail` from ``GET /api/flow/workflows/{id}``.

Invariants enforced by this module
----------------------------------

- :attr:`WorkflowDetail.flow` carries a raw :class:`dict` that
  validates against :class:`src.flow_loader.FlowSchema`. The repository
  loads every workflow through :class:`server.services.flow_validation.FlowValidator`
  so a broken workflow YAML never reaches the GUI.
"""

from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, ConfigDict


class WorkflowListItem(BaseModel):
    """One entry in the response of ``GET /api/flow/workflows``.

    Attributes:
        id (str): Stable workflow identifier (the YAML filename stem,
            for example ``"label_extraction_summary"``). Matches the
            path parameter of :meth:`WorkflowRepository.get`.
        label (str): Human-readable name. Taken from ``flow.name`` in
            the workflow YAML.
        description (str): Human-readable description. Taken from
            ``flow.description`` in the workflow YAML; empty string
            when the workflow omits it.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    description: str = ""


class WorkflowDetail(BaseModel):
    """Response of ``GET /api/flow/workflows/{workflow_id}``.

    Attributes:
        id (str): Stable workflow identifier, as on
            :class:`WorkflowListItem`.
        label (str): Human-readable name.
        description (str): Human-readable description.
        flow (Dict[str, Any]): Raw flow body, ready to be rehydrated
            into canvas nodes by the GUI codec or submitted to
            ``POST /api/schema/validate`` unchanged.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    description: str = ""
    flow: Dict[str, Any]
