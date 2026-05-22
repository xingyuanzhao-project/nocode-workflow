"""HTTP DTOs for the run-results preview and artifact download endpoints.

The GUI needs two views of a finished run's output:

- A small JSON preview of the first *N* rows, rendered as a table in
  the run page.
- A direct download of the full CSV artifact.

The DTOs in this module describe the JSON preview. The download endpoint
streams bytes and does not use a Pydantic response model.

Contents and relationships
--------------------------

- :class:`ArtifactName` — closed enum of the four output artifacts every
  run produces (``summary``, ``results``, ``states``, ``spans``).
- :class:`ResultsPreviewResponse` — body of
  ``GET /api/flow/runs/{run_id}/preview``.

How the rest of the system uses this module
-------------------------------------------

- :class:`server.services.results_preview.ResultsPreviewService` returns
  :class:`ResultsPreviewResponse` from
  :meth:`ResultsPreviewService.read_preview`.
- :class:`server.routes.results` consumes both the DTO and the enum.

Invariants enforced by this module
----------------------------------

- :class:`ArtifactName` is the single source of truth for which
  artifacts the GUI may request. Adding a new artifact (for example
  ``metrics``) requires adding a member here first; the service and
  route then fail closed on unknown members.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class ArtifactName(str, Enum):
    """Closed enum of the output artifacts a run emits.

    The string values match the filenames written by
    :class:`src.flow_builder.FlowRunner` under
    :attr:`server.storage.run_paths.RunPaths.output_dir`, with the
    ``.csv`` suffix stripped. Keeping the enum values filename-shaped
    makes URLs like ``/runs/<id>/artifacts/summary.csv`` trivially map
    onto the enum.

    Members:
        SUMMARY: ``summary.csv`` — the per-entity summary CSV, the
            primary output of every flow.
        RESULTS: ``results.csv`` — the per-entity classification or
            label-extraction results, present when the flow emits them.
        STATES: ``states.csv`` — the step-by-step state trace used for
            debugging.
        SPANS: ``spans.csv`` — the label extraction span offsets.
    """

    SUMMARY = "summary"
    RESULTS = "results"
    STATES = "states"
    SPANS = "spans"


class ResultsPreviewResponse(BaseModel):
    """Response of ``GET /api/flow/runs/{run_id}/preview``.

    Attributes:
        run_id (str): The queried run identifier.
        artifact_name (ArtifactName): Which output artifact was read.
        columns (List[str]): Column headers in the CSV, in column order.
        preview_rows (List[Dict[str, Any]]): First ``limit`` rows of the
            CSV, each represented as ``{column_name: cell_value}``. Cell
            values are coerced to JSON-safe primitives.
        total_row_count (int): Total number of rows in the CSV on disk,
            independent of ``limit``. The GUI uses this to display
            "showing 20 of 1,234" style captions.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str
    artifact_name: ArtifactName
    columns: List[str] = Field(default_factory=list)
    preview_rows: List[Dict[str, Any]] = Field(default_factory=list)
    total_row_count: int = 0
