"""HTTP DTOs for the run-results preview and output download endpoints.

The GUI needs two views of a finished run's output:

- A small JSON preview of the first *N* rows, rendered as a table in
  the run page.
- A direct download of the full CSV output.

The DTOs in this module describe the JSON preview. The download endpoint
streams bytes and does not use a Pydantic response model.

Contents and relationships
--------------------------

- :class:`ResultsPreviewResponse` — body of
  ``GET /api/flow/runs/{run_id}/preview``.

How the rest of the system uses this module
-------------------------------------------

- :class:`server.services.results_preview.ResultsPreviewService` returns
  :class:`ResultsPreviewResponse` from
  :meth:`ResultsPreviewService.read_preview`.
- :class:`server.routes.results` consumes the DTO.

Invariants enforced by this module
----------------------------------

- The preview endpoint reads the run's ``summary.csv`` directly; no
  artifact-name parameter is needed.
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class ResultsPreviewResponse(BaseModel):
    """Response of ``GET /api/flow/runs/{run_id}/preview``.

    Attributes:
        run_id (str): The queried run identifier.
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
    columns: List[str] = Field(default_factory=list)
    preview_rows: List[Dict[str, Any]] = Field(default_factory=list)
    total_row_count: int = 0
