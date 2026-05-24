"""Routes under ``/api/files`` — data file upload (CSV, JSON, JSONL).

Contents and relationships
--------------------------

- :data:`router` — :class:`fastapi.APIRouter` exposing
  ``POST /api/files/upload``.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.app` mounts :data:`router` at the root.

Invariants enforced by this module
----------------------------------

- The handler reads the upload body fully into memory before handing
  it to :class:`server.services.csv_uploader.CSVUploader`. The size
  cap lives on
  :attr:`server.settings.ServerSettings.max_upload_bytes`; exceeding
  it raises :class:`ValueError` which the error handlers translate to
  400.
"""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from starlette.responses import FileResponse

from server.dependencies import get_csv_uploader, get_server_paths
from server.schemas.files import (
    ColumnHeadersResponse,
    CSVUploadResponse,
    DataFileListResponse,
)
from server.services.csv_uploader import CSVUploader
from server.storage.paths import ServerPaths


def _get_project_root(paths: ServerPaths) -> Path:
    """Compute the project root from ServerPaths."""
    depth = len(PurePosixPath(paths.data_dir_relative_posix).parts)
    project_root = paths.data_dir
    for _ in range(depth):
        project_root = project_root.parent
    return project_root


def _resolve_stored_path(paths: ServerPaths, stored_path: str) -> Path:
    """Resolve a project-root-relative stored_path to an absolute Path."""
    project_root = _get_project_root(paths)
    resolved = (project_root / stored_path).resolve()
    if not resolved.is_relative_to(project_root.resolve()):
        raise HTTPException(
            status_code=400, detail="Path does not resolve inside the project"
        )
    return resolved


router = APIRouter(prefix="/api/files", tags=["files"])
"""Router exposing file-upload endpoints."""


@router.get("/columns", response_model=ColumnHeadersResponse)
def get_column_headers(
    path: str = Query(..., description="Project-root-relative stored_path of a data file"),
    paths: ServerPaths = Depends(get_server_paths),
) -> ColumnHeadersResponse:
    """Return column/field names for a stored data file.

    Supports CSV, JSON (array-of-records), and JSONL. For CSV only the
    header row is read. For JSON/JSONL only the first record is read to
    extract top-level field names.

    Args:
        path: The ``stored_path`` value as returned by the file list or
            upload endpoint.
        paths: Injected server paths.

    Returns:
        ColumnHeadersResponse: List of column/field name strings.
    """
    resolved = _resolve_stored_path(paths, path)

    if not resolved.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    extension = resolved.suffix.lower()

    if extension == ".csv":
        try:
            df = pd.read_csv(resolved, nrows=0)
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail=f"Cannot read CSV headers: {exc}"
            ) from exc
        return ColumnHeadersResponse(columns=[str(c) for c in df.columns.tolist()])

    if extension == ".jsonl":
        try:
            with open(resolved, "r", encoding="utf-8") as fh:
                first_line = fh.readline().strip()
            if not first_line:
                return ColumnHeadersResponse(columns=[])
            record = json.loads(first_line)
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail=f"Cannot read JSONL fields: {exc}"
            ) from exc
        if isinstance(record, dict):
            return ColumnHeadersResponse(columns=list(record.keys()))
        return ColumnHeadersResponse(columns=[])

    if extension == ".json":
        try:
            with open(resolved, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail=f"Cannot read JSON fields: {exc}"
            ) from exc
        if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            return ColumnHeadersResponse(columns=list(data[0].keys()))
        return ColumnHeadersResponse(columns=[])

    raise HTTPException(
        status_code=400,
        detail=f"Unsupported file extension {extension!r} for field introspection",
    )


@router.get("/list", response_model=DataFileListResponse)
def list_data_files(
    uploader: CSVUploader = Depends(get_csv_uploader),
) -> DataFileListResponse:
    """Return every uploaded and preloaded data file.

    Args:
        uploader (CSVUploader): Injected upload service.

    Returns:
        DataFileListResponse: Combined list of all available data files.
    """
    return uploader.list_files()


@router.post(
    "/upload",
    response_model=CSVUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_csv(
    file: UploadFile = File(...),
    uploader: CSVUploader = Depends(get_csv_uploader),
) -> CSVUploadResponse:
    """Accept a data file upload (CSV, JSON, or JSONL) and return its column descriptors.

    Args:
        file (UploadFile): The uploaded multipart file.
        uploader (CSVUploader): Injected upload service.

    Returns:
        CSVUploadResponse: Identifier, row count, and column
        descriptors for the stored file.
    """
    content = await file.read()
    return uploader.accept(filename=file.filename or "upload.csv", content=content)


@router.get("/download")
def download_file(
    path: str = Query(..., description="Project-root-relative stored_path"),
    paths: ServerPaths = Depends(get_server_paths),
) -> FileResponse:
    """Download a data or output file by its stored_path.

    Args:
        path: The ``stored_path`` value from the file list.
        paths: Injected server paths.

    Returns:
        FileResponse: The file with Content-Disposition attachment header.
    """
    project_root = _get_project_root(paths)
    resolved = (project_root / path).resolve()

    allowed_dirs = [
        paths.data_dir.resolve(),
        (project_root / "results_custom").resolve(),
    ]
    if not any(resolved.is_relative_to(d) for d in allowed_dirs):
        raise HTTPException(
            status_code=400,
            detail="Path does not resolve inside an allowed directory",
        )

    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    return FileResponse(
        path=str(resolved),
        filename=resolved.name,
        media_type="application/octet-stream",
    )
