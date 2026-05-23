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

from pathlib import Path, PurePosixPath

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from server.dependencies import get_csv_uploader, get_server_paths
from server.schemas.files import (
    ColumnHeadersResponse,
    CSVUploadResponse,
    DataFileListResponse,
)
from server.services.csv_uploader import CSVUploader
from server.storage.paths import ServerPaths


def _resolve_stored_path(paths: ServerPaths, stored_path: str) -> Path:
    """Resolve a project-root-relative stored_path to an absolute Path."""
    depth = len(PurePosixPath(paths.data_dir_relative_posix).parts)
    project_root = paths.data_dir
    for _ in range(depth):
        project_root = project_root.parent
    resolved = (project_root / stored_path).resolve()
    if not resolved.is_relative_to(paths.data_dir):
        raise HTTPException(
            status_code=400, detail="Path does not resolve inside data directory"
        )
    return resolved


router = APIRouter(prefix="/api/files", tags=["files"])
"""Router exposing file-upload endpoints."""


@router.get("/columns", response_model=ColumnHeadersResponse)
def get_column_headers(
    path: str = Query(..., description="Project-root-relative stored_path of the CSV"),
    paths: ServerPaths = Depends(get_server_paths),
) -> ColumnHeadersResponse:
    """Return column headers for a stored CSV file.

    Only CSV files are supported; JSON/JSONL files do not have fixed
    column headers.

    Args:
        path: The ``stored_path`` value as returned by the file list or
            upload endpoint (e.g. ``server/data/uploads/<id>.csv``).
        paths: Injected server paths.

    Returns:
        ColumnHeadersResponse: List of column header strings.
    """
    resolved = _resolve_stored_path(paths, path)

    if not resolved.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    if resolved.suffix.lower() != ".csv":
        raise HTTPException(
            status_code=400,
            detail="Column header introspection is only supported for CSV files",
        )

    try:
        df = pd.read_csv(resolved, nrows=0)
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Cannot read CSV headers: {exc}"
        ) from exc

    return ColumnHeadersResponse(columns=[str(c) for c in df.columns.tolist()])


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
