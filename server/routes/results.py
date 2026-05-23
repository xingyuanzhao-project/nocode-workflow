"""Routes under ``/api/flow/runs/{run_id}/...`` for run output.

Two endpoints live here:

- ``GET /api/flow/runs/{run_id}/preview`` — JSON preview of the first
  *N* rows of the output CSV, for the in-GUI results table.
- ``GET /api/flow/runs/{run_id}/output`` — streamed CSV download of
  the output file.

Both endpoints are backed by
:class:`server.services.results_preview.ResultsPreviewService`; the
route layer only translates HTTP concerns (query parsing, status
codes, ``Content-Disposition``).

Contents and relationships
--------------------------

- :data:`router` — :class:`fastapi.APIRouter` mounted under
  ``/api/flow`` (not ``/api/flow/runs``) so the same prefix as
  :mod:`server.routes.flow` keeps the URL tree flat.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.app` mounts :data:`router` in :func:`create_app`.
- The GUI's ``ResultsPreviewTable`` component calls ``preview``; the
  download button calls ``output``.

Invariants enforced by this module
----------------------------------

- The download handler returns 404 for missing files because the
  service raises :class:`FileNotFoundError`, which
  :mod:`server.errors` translates to a 404 response.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from starlette.responses import FileResponse

from server.dependencies import get_results_preview_service
from server.schemas.results import ResultsPreviewResponse
from server.services.results_preview import ResultsPreviewService


router = APIRouter(prefix="/api/flow", tags=["results"])
"""Router exposing the run-results preview and output download endpoints."""


DEFAULT_PREVIEW_ROW_LIMIT: int = 20
"""Default number of rows returned by ``GET .../preview`` when omitted."""

MAX_PREVIEW_ROW_LIMIT: int = 500
"""Upper bound on the ``limit`` query parameter of ``GET .../preview``.

Kept deliberately small so the JSON payload stays cheap. Clients that
need more rows should download the CSV directly.
"""


@router.get(
    "/runs/{run_id}/preview",
    response_model=ResultsPreviewResponse,
)
def preview_run_output(
    run_id: str,
    limit: int = Query(
        default=DEFAULT_PREVIEW_ROW_LIMIT,
        ge=0,
        le=MAX_PREVIEW_ROW_LIMIT,
        description="Maximum number of rows to include in the preview.",
    ),
    service: ResultsPreviewService = Depends(get_results_preview_service),
) -> ResultsPreviewResponse:
    """Return a JSON preview of a run's output CSV.

    Args:
        run_id (str): The run identifier.
        limit (int): Maximum number of rows to return. Defaults to
            :data:`DEFAULT_PREVIEW_ROW_LIMIT`; capped at
            :data:`MAX_PREVIEW_ROW_LIMIT`.
        service (ResultsPreviewService): Injected service.

    Returns:
        ResultsPreviewResponse: Columns, preview rows, and total row
        count.
    """
    return service.read_preview(run_id, limit)


@router.get("/runs/{run_id}/output")
def download_run_output(
    run_id: str,
    service: ResultsPreviewService = Depends(get_results_preview_service),
) -> FileResponse:
    """Stream a run's output CSV as a downloadable file.

    Args:
        run_id (str): The run identifier.
        service (ResultsPreviewService): Injected service used only for
            its path-resolution method.

    Returns:
        FileResponse: 200 response with ``text/csv`` body and a
        ``Content-Disposition: attachment`` header naming the file
        ``<run_id>_summary.csv``. Missing files surface as 404
        via :mod:`server.errors`.
    """
    output_path = service.resolve_output_path(run_id)
    download_filename = f"{run_id}_summary.csv"
    return FileResponse(
        path=output_path,
        media_type="text/csv",
        filename=download_filename,
    )
