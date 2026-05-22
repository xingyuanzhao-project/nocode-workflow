"""HTTP DTOs for the CSV upload endpoint.

Contents and relationships
--------------------------

- :class:`CSVColumnDescriptor` — one column of the uploaded CSV.
- :class:`CSVUploadResponse` — full response of
  ``POST /api/files/upload``.

How the rest of the system uses this module
-------------------------------------------

- :class:`server.services.csv_uploader.CSVUploader` returns
  :class:`CSVUploadResponse` from :meth:`CSVUploader.accept`.
"""

from __future__ import annotations

from typing import Any, List

from pydantic import BaseModel, ConfigDict, Field


class CSVColumnDescriptor(BaseModel):
    """One column of the uploaded CSV.

    Attributes:
        name (str): Column header string.
        dtype (str): Pandas dtype string (for example ``"object"`` or
            ``"int64"``).
        sample_values (List[Any]): First few non-null values, capped by
            :class:`server.services.csv_uploader.CSVUploader`. Used by
            the GUI to let the user eyeball column roles.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    dtype: str
    sample_values: List[Any] = Field(default_factory=list)


class CSVUploadResponse(BaseModel):
    """Response of ``POST /api/files/upload``.

    Attributes:
        upload_id (str): Identifier assigned to the stored CSV.
        filename (str): Original filename as submitted by the client.
        stored_path (str): Project-root-relative POSIX path where the
            server persisted the CSV (for example
            ``server/data/uploads/<upload_id>.csv``). Clients paste
            this string verbatim into
            :attr:`src.flow_loader.DataConfig.input_csv` when building
            a flow. The path is portable across the FastAPI web process
            (which may run on Windows during development) and the
            Celery worker container (Linux) because both processes
            share the same project root as their working directory.
        row_count (int): Number of rows in the CSV, excluding header.
        columns (List[CSVColumnDescriptor]): One descriptor per column.
    """

    model_config = ConfigDict(extra="forbid")

    upload_id: str
    filename: str
    stored_path: str
    row_count: int
    columns: List[CSVColumnDescriptor] = Field(default_factory=list)
