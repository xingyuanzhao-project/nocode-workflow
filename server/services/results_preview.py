"""Service that reads run output from disk.

Every finished run writes a ``summary.csv`` under the run directory.
This service owns the read side of that contract: the GUI asks for
either a small JSON preview (for the in-app results table) or the
absolute path of the output file (for the download endpoint), and this
service answers from :class:`ResultsPreviewResponse` and
:class:`pathlib.Path` respectively.

Contents and relationships
--------------------------

- :class:`ResultsPreviewService` — the service.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.routes.results` calls :meth:`read_preview` from
  ``GET /api/flow/runs/{run_id}/preview`` and
  :meth:`resolve_output_path` from
  ``GET /api/flow/runs/{run_id}/output``.

Invariants enforced by this module
----------------------------------

- The service never writes. Output is produced by the worker; the
  web process only reads it.
- Requests for a run whose output does not yet exist raise
  :class:`FileNotFoundError` so the route layer can translate it to a
  404 through :mod:`server.errors`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from server.schemas.results import ResultsPreviewResponse
from server.storage.paths import ServerPaths
from server.storage.run_paths import RunPaths

_OUTPUT_FILENAME: str = "summary.csv"
"""Filename written by :class:`src.flow_builder.FlowRunner` for the
primary output artifact."""


class ResultsPreviewService:
    """Read-side service for run output.

    Attributes:
        paths (ServerPaths): Top-level on-disk layout. Only
            :attr:`ServerPaths.runs_dir` is read.

    Methods:
        read_preview: Return a JSON preview of the first ``limit`` rows
            of the output CSV.
        resolve_output_path: Return the absolute path of the output CSV,
            raising :class:`FileNotFoundError` when the file does not
            exist.
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
        limit: int,
    ) -> ResultsPreviewResponse:
        """Return the first ``limit`` rows of the output CSV as JSON.

        The total row count is determined from a second, streaming read
        that counts rows without materialising the entire dataframe.
        For typical flow outputs (thousands of rows, dozens of columns)
        this is fast enough; if it ever becomes a bottleneck the
        service can cache the count in a sidecar file.

        Args:
            run_id (str): The run identifier.
            limit (int): Maximum number of rows to include in
                ``preview_rows``. Must be non-negative.

        Returns:
            ResultsPreviewResponse: Columns, preview rows, and the total
            row count. ``columns`` and ``preview_rows`` are empty when
            the CSV is empty; ``total_row_count`` is ``0`` in that case
            too.

        Raises:
            ValueError: If ``limit`` is negative.
            FileNotFoundError: If the output does not exist for
                ``run_id``.
        """
        if limit < 0:
            raise ValueError(f"limit must be non-negative; got {limit}")

        output_path = self.resolve_output_path(run_id)

        preview_dataframe = pd.read_csv(output_path, nrows=limit)
        column_names: List[str] = [str(name) for name in preview_dataframe.columns]
        preview_rows: List[Dict[str, Any]] = [
            {
                column_name: _jsonable_cell(row_record.get(column_name))
                for column_name in column_names
            }
            for row_record in preview_dataframe.to_dict(orient="records")
        ]

        total_row_count = _count_rows_excluding_header(output_path)

        return ResultsPreviewResponse(
            run_id=run_id,
            columns=column_names,
            preview_rows=preview_rows,
            total_row_count=total_row_count,
        )

    def resolve_output_path(self, run_id: str) -> Path:
        """Return the absolute path of the output CSV for ``run_id``.

        Args:
            run_id (str): The run identifier.

        Returns:
            Path: Absolute path to the CSV on disk.

        Raises:
            FileNotFoundError: If the file does not exist. The message
                includes both the ``run_id`` and the resolved path so
                operators can debug quickly.
        """
        run_paths = RunPaths.for_run_id(self.paths, run_id)
        output_path = run_paths.output_dir / _OUTPUT_FILENAME
        if not output_path.is_file():
            raise FileNotFoundError(
                f"Output not found for run '{run_id}' at {output_path}."
            )
        return output_path


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
