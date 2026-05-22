"""Service that reads run output artifacts from disk.

Every finished run writes up to four CSVs under
:attr:`server.storage.run_paths.RunPaths.output_dir`. This service owns
the read side of that contract: the GUI asks for either a small JSON
preview (for the in-app results table) or the absolute path of the
artifact (for the download endpoint), and this service answers from
:class:`ResultsPreviewResponse` and :class:`pathlib.Path` respectively.

Contents and relationships
--------------------------

- :class:`ResultsPreviewService` — the service.
- :data:`_ARTIFACT_FILENAMES` — mapping from
  :class:`server.schemas.results.ArtifactName` to the CSV filename
  written by :class:`src.flow_builder.FlowRunner`.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.routes.results` calls :meth:`read_preview` from
  ``GET /api/flow/runs/{run_id}/preview`` and
  :meth:`resolve_artifact_path` from
  ``GET /api/flow/runs/{run_id}/artifacts/{artifact_name}``.

Invariants enforced by this module
----------------------------------

- The service never writes. Artifacts are produced by the worker; the
  web process only reads them.
- The mapping in :data:`_ARTIFACT_FILENAMES` is the single source of
  truth for how :class:`ArtifactName` translates to a filename; changing
  one requires changing the other. The mapping is validated against the
  enum membership at import time.
- Requests for an artifact that does not yet exist raise
  :class:`FileNotFoundError` so the route layer can translate it to a
  404 through :mod:`server.errors`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from server.schemas.results import ArtifactName, ResultsPreviewResponse
from server.storage.paths import ServerPaths
from server.storage.run_paths import RunPaths


_ARTIFACT_FILENAMES: Dict[ArtifactName, str] = {
    ArtifactName.SUMMARY: "summary.csv",
    ArtifactName.RESULTS: "results.csv",
    ArtifactName.STATES: "states.csv",
    ArtifactName.SPANS: "spans.csv",
}
"""Filename written by :class:`src.flow_builder.FlowRunner` per artifact.

Kept module-private so the only legal way to get a filename from an
:class:`ArtifactName` is through :meth:`ResultsPreviewService.resolve_artifact_path`.
"""


assert set(_ARTIFACT_FILENAMES.keys()) == set(
    ArtifactName
), "_ARTIFACT_FILENAMES must cover every ArtifactName member"


class ResultsPreviewService:
    """Read-side service for run output artifacts.

    Attributes:
        paths (ServerPaths): Top-level on-disk layout. Only
            :attr:`ServerPaths.runs_dir` is read.

    Methods:
        read_preview: Return a JSON preview of the first ``limit`` rows
            of an artifact CSV.
        resolve_artifact_path: Return the absolute path of an artifact
            CSV, raising :class:`FileNotFoundError` when the file does
            not exist.
    """

    def __init__(self, paths: ServerPaths) -> None:
        """Store the injected paths.

        Args:
            paths (ServerPaths): Top-level on-disk layout.
        """
        self.paths = paths

    def read_preview(
        self,
        run_id: str,
        artifact_name: ArtifactName,
        limit: int,
    ) -> ResultsPreviewResponse:
        """Return the first ``limit`` rows of an artifact CSV as JSON.

        The total row count is determined from a second, streaming read
        that counts rows without materialising the entire dataframe.
        For typical flow outputs (thousands of rows, dozens of columns)
        this is fast enough; if it ever becomes a bottleneck the
        service can cache the count in a sidecar file.

        Args:
            run_id (str): The run identifier.
            artifact_name (ArtifactName): Which artifact to read.
            limit (int): Maximum number of rows to include in
                ``preview_rows``. Must be non-negative.

        Returns:
            ResultsPreviewResponse: Columns, preview rows, and the total
            row count. ``columns`` and ``preview_rows`` are empty when
            the CSV is empty; ``total_row_count`` is ``0`` in that case
            too.

        Raises:
            ValueError: If ``limit`` is negative.
            FileNotFoundError: If the artifact does not exist for
                ``run_id``.
        """
        if limit < 0:
            raise ValueError(f"limit must be non-negative; got {limit}")

        artifact_path = self.resolve_artifact_path(run_id, artifact_name)

        preview_dataframe = pd.read_csv(artifact_path, nrows=limit)
        column_names: List[str] = [str(name) for name in preview_dataframe.columns]
        preview_rows: List[Dict[str, Any]] = [
            {
                column_name: _jsonable_cell(row_record.get(column_name))
                for column_name in column_names
            }
            for row_record in preview_dataframe.to_dict(orient="records")
        ]

        total_row_count = _count_rows_excluding_header(artifact_path)

        return ResultsPreviewResponse(
            run_id=run_id,
            artifact_name=artifact_name,
            columns=column_names,
            preview_rows=preview_rows,
            total_row_count=total_row_count,
        )

    def resolve_artifact_path(
        self, run_id: str, artifact_name: ArtifactName
    ) -> Path:
        """Return the absolute path of the artifact CSV for ``run_id``.

        Args:
            run_id (str): The run identifier.
            artifact_name (ArtifactName): Which artifact to resolve.

        Returns:
            Path: Absolute path to the CSV on disk.

        Raises:
            FileNotFoundError: If the file does not exist. The message
                includes both the ``run_id`` and the resolved path so
                operators can debug quickly.
        """
        run_paths = RunPaths.for_run_id(self.paths, run_id)
        filename = _ARTIFACT_FILENAMES[artifact_name]
        artifact_path = run_paths.output_dir / filename
        if not artifact_path.is_file():
            raise FileNotFoundError(
                f"Artifact '{artifact_name.value}' not found for run "
                f"'{run_id}' at {artifact_path}."
            )
        return artifact_path


def _count_rows_excluding_header(csv_path: Path) -> int:
    """Count data rows in ``csv_path`` without loading the whole file.

    The count excludes the header row. Streaming the file line by line
    keeps memory bounded even for multi-gigabyte CSVs.

    Args:
        csv_path (Path): Absolute path to the CSV to count.

    Returns:
        int: Number of data rows (header excluded). ``0`` when the file
        contains only a header or is empty.
    """
    with csv_path.open("r", encoding="utf-8", newline="") as file_handle:
        first_line = file_handle.readline()
        if not first_line:
            return 0
        return sum(1 for _ in file_handle)


def _jsonable_cell(value: object) -> object:
    """Coerce a pandas cell value to a JSON-serialisable primitive.

    Args:
        value (object): Value pulled from a pandas row record.

    Returns:
        object: ``value`` itself when already JSON-safe (``str``, ``int``,
        ``float``, ``bool``, ``None``); otherwise ``str(value)``. NaN
        is returned as ``None`` so the GUI sees a missing value, not
        ``"nan"``.
    """
    if value is None:
        return None
    if isinstance(value, float) and value != value:  # NaN check without importing math
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


__all__ = ["ResultsPreviewService"]
