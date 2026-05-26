"""Service that reads run output from disk.

A finished run writes one or more output files (``summary.csv``,
``summary_1.json``, etc.) under the run directory. This service owns
the read side: the GUI asks for a JSON preview of all outputs, and
this service answers with :class:`ResultsPreviewResponse`.

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

import json as _json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from server.schemas.results import OutputArtifact, ResultsPreviewResponse
from server.storage.paths import ServerPaths
from server.storage.run_paths import RunPaths

_OUTPUT_FILENAME: str = "summary.csv"
_OUTPUT_EXTENSIONS: frozenset = frozenset({".csv", ".json"})


class ResultsPreviewService:
    """Read-side service for run output."""

    def __init__(self, paths: ServerPaths) -> None:
        self.paths = paths

    def _discover_output_files(self, run_paths: RunPaths) -> List[Path]:
        """Find all output files in a run directory, ordered primary-first."""
        output_dir = run_paths.output_dir
        if not output_dir.is_dir():
            return []
        primary = output_dir / _OUTPUT_FILENAME
        files: List[Path] = []
        if primary.is_file():
            files.append(primary)
        for p in sorted(output_dir.iterdir()):
            if p == primary:
                continue
            if p.suffix.lower() in _OUTPUT_EXTENSIONS and p.stem.startswith("summary"):
                files.append(p)
        return files

    def _preview_one_file(
        self, file_path: Path, limit: int,
    ) -> OutputArtifact:
        """Build a preview artifact for one output file."""
        ext = file_path.suffix.lower()
        if ext == ".json":
            return self._preview_json(file_path, limit)
        return self._preview_csv(file_path, limit)

    def _preview_csv(self, file_path: Path, limit: int) -> OutputArtifact:
        preview_df = pd.read_csv(file_path, nrows=limit)
        columns = [str(c) for c in preview_df.columns]
        rows: List[Dict[str, Any]] = [
            {col: _jsonable_cell(rec.get(col)) for col in columns}
            for rec in preview_df.to_dict(orient="records")
        ]
        total = _count_rows_excluding_header(file_path)
        return OutputArtifact(
            filename=file_path.name,
            format="csv",
            columns=columns,
            preview_rows=rows,
            total_row_count=total,
        )

    def _preview_json(self, file_path: Path, limit: int) -> OutputArtifact:
        raw = file_path.read_text(encoding="utf-8")
        try:
            records = _json.loads(raw)
        except _json.JSONDecodeError:
            records = []
        if not isinstance(records, list):
            records = [records] if records else []
        total = len(records)
        preview = records[:limit]
        columns = list(preview[0].keys()) if preview else []
        rows: List[Dict[str, Any]] = [
            {col: _jsonable_cell(r.get(col)) for col in columns}
            for r in preview
        ]
        return OutputArtifact(
            filename=file_path.name,
            format="json",
            columns=columns,
            preview_rows=rows,
            total_row_count=total,
        )

    def read_preview(
        self,
        run_id: str,
        limit: int,
    ) -> ResultsPreviewResponse:
        """Return previews of all output files for a run.

        The top-level ``columns``, ``preview_rows``, and
        ``total_row_count`` fields are populated from the primary output
        (``summary.csv``) for backward compatibility. The ``outputs``
        list contains previews for ALL output files.
        """
        if limit < 0:
            raise ValueError(f"limit must be non-negative; got {limit}")

        run_paths = RunPaths.for_run_id(self.paths, run_id)
        output_files = self._discover_output_files(run_paths)
        if not output_files:
            raise FileNotFoundError(
                f"No output files found for run '{run_id}' "
                f"in {run_paths.output_dir}."
            )

        artifacts: List[OutputArtifact] = [
            self._preview_one_file(f, limit) for f in output_files
        ]

        primary = artifacts[0]
        return ResultsPreviewResponse(
            run_id=run_id,
            columns=primary.columns,
            preview_rows=primary.preview_rows,
            total_row_count=primary.total_row_count,
            outputs=artifacts,
        )

    def resolve_output_path(self, run_id: str, filename: str = _OUTPUT_FILENAME) -> Path:
        """Return the absolute path of an output file for ``run_id``."""
        run_paths = RunPaths.for_run_id(self.paths, run_id)
        output_path = run_paths.output_dir / filename
        if not output_path.is_file():
            raise FileNotFoundError(
                f"Output not found for run '{run_id}' at {output_path}."
            )
        return output_path


def _count_rows_excluding_header(csv_path: Path) -> int:
    """Count data rows in a CSV without loading the whole file."""
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        first_line = fh.readline()
        if not first_line:
            return 0
        return sum(1 for _ in fh)


def _jsonable_cell(value: object) -> object:
    """Coerce a pandas cell value to a JSON-serialisable primitive."""
    if value is None:
        return None
    if isinstance(value, float) and value != value:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


__all__ = ["ResultsPreviewService"]
