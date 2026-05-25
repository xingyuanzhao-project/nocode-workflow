"""Service that accepts uploaded data files and inspects their columns.

The GUI uploads a data file (CSV, JSON, or JSONL) through
``POST /api/files/upload``. This service validates the size, parses
the file into a DataFrame, writes the raw bytes to
:attr:`server.storage.paths.ServerPaths.data_dir`, and returns a
small DTO describing the columns so the GUI can display column
information.

Contents and relationships
--------------------------

- :func:`parse_tabular_upload` — standalone parser that dispatches to the
  appropriate pandas reader based on filename extension.
- :class:`CSVUploader` — the service.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.routes.files` calls :meth:`CSVUploader.accept` from the
  ``POST /api/files/upload`` handler.

Invariants enforced by this module
----------------------------------

- Uploads larger than
  :attr:`server.settings.ServerSettings.max_upload_bytes` are rejected
  with :class:`ValueError`.
- Every stored file lives at
  ``<data_dir>/<upload_id><ext>`` where ``upload_id`` is a UUID4
  and ``<ext>`` is the original file extension (``.csv``, ``.json``,
  or ``.jsonl``).
- Sample values per column are capped at :data:`SAMPLE_VALUES_PER_COLUMN`
  so the response DTO stays small even for wide files.
"""

from __future__ import annotations

import uuid
from io import BytesIO
from pathlib import PurePosixPath
from typing import List

import pandas as pd

from server.schemas.files import (
    CSVColumnDescriptor,
    CSVUploadResponse,
    DataFileListItem,
    DataFileListResponse,
)
from server.settings import ServerSettings
from server.storage.paths import ServerPaths

SAMPLE_VALUES_PER_COLUMN: int = 5
"""Maximum number of sample values returned per column."""

SUPPORTED_UPLOAD_EXTENSIONS: frozenset[str] = frozenset({".csv", ".json", ".jsonl"})
"""File extensions accepted by the upload endpoint."""


def parse_tabular_upload(filename: str, content: bytes) -> pd.DataFrame:
    """Parse uploaded bytes into a DataFrame based on filename extension.

    Args:
        filename (str): Original filename whose extension selects the
            parser (``.csv``, ``.json``, or ``.jsonl``).
        content (bytes): Raw file bytes.

    Returns:
        pd.DataFrame: The parsed tabular data.

    Raises:
        ValueError: If the extension is not in
            :data:`SUPPORTED_UPLOAD_EXTENSIONS` or the content cannot
            be parsed.
    """
    extension = PurePosixPath(filename).suffix.lower()
    if extension not in SUPPORTED_UPLOAD_EXTENSIONS:
        raise ValueError(
            f"Unsupported file extension {extension!r}; "
            f"accepted extensions are {sorted(SUPPORTED_UPLOAD_EXTENSIONS)}"
        )

    buffer = BytesIO(content)
    if extension == ".csv":
        try:
            return pd.read_csv(buffer)
        except (pd.errors.EmptyDataError, pd.errors.ParserError) as parse_error:
            raise ValueError(
                f"Uploaded file is not a valid CSV: {parse_error}"
            ) from parse_error
    elif extension == ".json":
        try:
            return pd.read_json(buffer, orient="records")
        except ValueError as parse_error:
            raise ValueError(
                f"Uploaded file is not valid JSON (expected array of records): "
                f"{parse_error}"
            ) from parse_error
    elif extension == ".jsonl":
        try:
            return pd.read_json(buffer, lines=True)
        except ValueError as parse_error:
            raise ValueError(
                f"Uploaded file is not valid JSONL: {parse_error}"
            ) from parse_error

    raise ValueError(f"Unhandled extension {extension!r}")


class CSVUploader:
    """Service that validates, stores, and describes uploaded data files.

    Despite the class name (kept for backward compatibility), this service
    accepts CSV, JSON, and JSONL uploads.

    Attributes:
        paths (ServerPaths): On-disk layout; only
            :attr:`ServerPaths.data_dir` is read.
        settings (ServerSettings): Process settings; only
            :attr:`ServerSettings.max_upload_bytes` is read.

    Methods:
        accept: Store a data file payload on disk and return its column
            descriptor DTO.
    """

    def __init__(self, paths: ServerPaths, settings: ServerSettings) -> None:
        """Store the injected paths and settings.

        Args:
            paths (ServerPaths): On-disk layout.
            settings (ServerSettings): Process settings.
        """
        self.paths = paths
        self.settings = settings

    def accept(self, filename: str, content: bytes) -> CSVUploadResponse:
        """Validate, persist, and describe an uploaded data file.

        Accepts ``.csv``, ``.json``, and ``.jsonl`` uploads. The file
        is stored with its original extension so the flow loader can
        dispatch to the correct pandas reader at run time.

        Args:
            filename (str): Original filename as submitted by the
                client. Its extension determines the parser and the
                stored file suffix.
            content (bytes): Raw bytes of the data file.

        Returns:
            CSVUploadResponse: Identifier, row count, and column
            descriptors for the stored file.

        Raises:
            ValueError: If the payload exceeds
                :attr:`server.settings.ServerSettings.max_upload_bytes`,
                if the extension is unsupported, or if the content
                cannot be parsed.
        """
        if len(content) > self.settings.max_upload_bytes:
            raise ValueError(
                f"File upload is {len(content)} bytes; limit is "
                f"{self.settings.max_upload_bytes} bytes."
            )

        dataframe = parse_tabular_upload(filename, content)
        extension = PurePosixPath(filename).suffix.lower()

        upload_id = uuid.uuid4().hex
        destination = self.paths.data_dir / f"{upload_id}{extension}"
        with destination.open("wb") as file_handle:
            file_handle.write(content)
        stored_path = (
            f"{self.paths.data_dir_relative_posix}/{upload_id}{extension}"
        )

        columns = [
            self._describe_column(dataframe, column_name)
            for column_name in dataframe.columns
        ]
        return CSVUploadResponse(
            upload_id=upload_id,
            filename=filename,
            stored_path=stored_path,
            row_count=int(len(dataframe)),
            columns=columns,
        )

    def list_files(self) -> DataFileListResponse:
        """List every data file in uploads, preloaded data, and results directories.

        Returns:
            DataFileListResponse: One entry per file (uploaded data files
            and pipeline output files).
        """
        items: list[DataFileListItem] = []

        for file_path in sorted(self.paths.data_dir.iterdir()):
            if file_path.suffix.lower() in SUPPORTED_UPLOAD_EXTENSIONS:
                stored_path = (
                    f"{self.paths.data_dir_relative_posix}/{file_path.name}"
                )
                items.append(
                    DataFileListItem(
                        filename=file_path.name,
                        stored_path=stored_path,
                        row_count=None,
                        source="uploaded",
                    )
                )

        project_root = self.paths.data_dir
        depth = len(PurePosixPath(self.paths.data_dir_relative_posix).parts)
        for _ in range(depth):
            project_root = project_root.parent
        preloaded_dir = project_root / "data"
        results_dir = project_root / "results_custom"

        if preloaded_dir.exists():
            for file_path in sorted(preloaded_dir.rglob("*")):
                if (
                    file_path.is_file()
                    and file_path.suffix.lower() in SUPPORTED_UPLOAD_EXTENSIONS
                ):
                    stored_path = file_path.relative_to(project_root).as_posix()
                    items.append(
                        DataFileListItem(
                            filename=file_path.name,
                            stored_path=stored_path,
                            row_count=None,
                            source="preloaded",
                        )
                    )

        if results_dir.exists():
            output_extensions = frozenset({".csv", ".json"})
            for file_path in sorted(results_dir.rglob("*")):
                if file_path.is_file() and file_path.suffix.lower() in output_extensions:
                    stored_path = file_path.relative_to(project_root).as_posix()
                    items.append(
                        DataFileListItem(
                            filename=file_path.name,
                            stored_path=stored_path,
                            row_count=None,
                            source="output",
                        )
                    )

        return DataFileListResponse(files=items)

    @staticmethod
    def _describe_column(
        dataframe: pd.DataFrame, column_name: str
    ) -> CSVColumnDescriptor:
        """Describe one column of ``dataframe`` by dtype and sample values.

        Args:
            dataframe (pd.DataFrame): Source dataframe.
            column_name (str): Column header to describe.

        Returns:
            CSVColumnDescriptor: Column descriptor DTO.
        """
        column = dataframe[column_name]
        sample_values = [
            _jsonable_cell(value)
            for value in column.dropna().head(SAMPLE_VALUES_PER_COLUMN).tolist()
        ]
        return CSVColumnDescriptor(
            name=str(column_name),
            dtype=str(column.dtype),
            sample_values=sample_values,
        )


def _jsonable_cell(value: object) -> object:
    """Convert ``value`` into a JSON-serialisable primitive when needed.

    Args:
        value (object): Value pulled from a pandas Series.

    Returns:
        object: ``value`` itself when already JSON-compatible, otherwise
        its ``str()`` representation.
    """
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


__all__: List[str] = ["CSVUploader"]
