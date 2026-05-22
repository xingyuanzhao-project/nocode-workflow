"""HTTP DTOs for the flow-template endpoints.

The GUI shows a "New Flow" dialog with a short list of preset templates,
and then loads the chosen template onto the canvas. Two DTOs cover
those two steps:

- :class:`FlowTemplateListItem` — compact list-view entry (no flow body).
- :class:`FlowTemplateDetail` — full detail view including the raw flow
  body the GUI rehydrates into canvas nodes.

Contents and relationships
--------------------------

- :class:`FlowTemplateListItem` — returned by
  :class:`server.services.template_repository.TemplateRepository.list`.
- :class:`FlowTemplateDetail` — returned by
  :meth:`TemplateRepository.get`.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.routes.templates` consumes both DTOs and exposes them
  over HTTP.
- The GUI's ``NewFlowDialog`` component reads
  :class:`FlowTemplateListItem` from ``GET /api/flow/templates`` and
  :class:`FlowTemplateDetail` from ``GET /api/flow/templates/{id}``.

Invariants enforced by this module
----------------------------------

- :attr:`FlowTemplateDetail.flow` carries a raw :class:`dict` that
  validates against :class:`src.flow_loader.FlowSchema`. The repository
  loads every template through :class:`server.services.flow_validation.FlowValidator`
  so a broken template YAML never reaches the GUI.
"""

from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, ConfigDict


class FlowTemplateListItem(BaseModel):
    """One entry in the response of ``GET /api/flow/templates``.

    Attributes:
        id (str): Stable template identifier (the YAML filename stem,
            for example ``"label_extraction_summary"``). Matches the
            path parameter of :meth:`TemplateRepository.get`.
        label (str): Human-readable name. Taken from ``flow.name`` in
            the template YAML.
        description (str): Human-readable description. Taken from
            ``flow.description`` in the template YAML; empty string
            when the template omits it.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    description: str = ""


class FlowTemplateDetail(BaseModel):
    """Response of ``GET /api/flow/templates/{template_id}``.

    Attributes:
        id (str): Stable template identifier, as on
            :class:`FlowTemplateListItem`.
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
