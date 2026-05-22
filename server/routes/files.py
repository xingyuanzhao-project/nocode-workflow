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

from fastapi import APIRouter, Depends, File, UploadFile, status

from server.dependencies import get_csv_uploader
from server.schemas.files import CSVUploadResponse
from server.services.csv_uploader import CSVUploader


router = APIRouter(prefix="/api/files", tags=["files"])
"""Router exposing file-upload endpoints."""


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
