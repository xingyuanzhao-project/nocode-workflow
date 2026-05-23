"""Unit tests for :class:`server.services.csv_uploader.CSVUploader`.

Covers the happy path, oversize, malformed CSV, and the
``sample_values_per_column`` cap on a wide CSV.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from server.services.csv_uploader import SAMPLE_VALUES_PER_COLUMN, CSVUploader


@pytest.fixture
def csv_uploader(server_paths, isolated_server_settings) -> CSVUploader:
    """Build a :class:`CSVUploader` against the isolated fixtures.

    Returns:
        CSVUploader: Uploader ready to accept bytes.
    """
    return CSVUploader(paths=server_paths, settings=isolated_server_settings)


class TestCSVUploaderAccept:
    def test_stores_file_under_uploads_dir(
        self,
        csv_uploader: CSVUploader,
        tiny_csv_bytes: bytes,
        server_paths,
    ) -> None:
        response = csv_uploader.accept("tiny.csv", tiny_csv_bytes)
        destination = server_paths.uploads_dir / f"{response.upload_id}.csv"
        assert destination.is_file()
        assert destination.read_bytes() == tiny_csv_bytes

    def test_stored_path_is_project_root_relative_posix(
        self,
        csv_uploader: CSVUploader,
        tiny_csv_bytes: bytes,
        server_paths,
    ) -> None:
        response = csv_uploader.accept("tiny.csv", tiny_csv_bytes)
        assert response.stored_path.startswith(server_paths.uploads_dir_relative_posix)
        assert "\\" not in response.stored_path
        assert not response.stored_path.startswith("/")

    def test_response_preserves_filename_and_row_count(
        self, csv_uploader: CSVUploader, tiny_csv_bytes: bytes
    ) -> None:
        response = csv_uploader.accept("tiny.csv", tiny_csv_bytes)
        assert response.filename == "tiny.csv"
        # Fixture ``tiny.csv`` has 5 data rows.
        assert response.row_count == 5
        assert [c.name for c in response.columns] == ["text", "victim", "index"]


class TestCSVUploaderRejects:
    def test_oversize_rejected(
        self, csv_uploader: CSVUploader, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Shrink the limit rather than build a huge payload.
        monkeypatch.setattr(csv_uploader.settings, "max_upload_bytes", 10)
        oversized = b"text,victim,index\n" + b"a,b,c\n" * 50
        with pytest.raises(ValueError, match="limit is 10 bytes"):
            csv_uploader.accept("too_big.csv", oversized)

    def test_empty_payload_rejected(self, csv_uploader: CSVUploader) -> None:
        with pytest.raises(ValueError, match="not a valid CSV"):
            csv_uploader.accept("empty.csv", b"")


class TestCSVUploaderSampleCap:
    def test_sample_values_capped_per_column(
        self, csv_uploader: CSVUploader
    ) -> None:
        rows = 50
        dataframe = pd.DataFrame(
            {"alpha": range(rows), "bravo": [f"v{i}" for i in range(rows)]}
        )
        csv_bytes = dataframe.to_csv(index=False).encode("utf-8")
        response = csv_uploader.accept("wide.csv", csv_bytes)
        for column in response.columns:
            assert len(column.sample_values) <= SAMPLE_VALUES_PER_COLUMN


class TestCSVUploaderListFiles:
    def test_includes_preloaded_project_data_files(
        self, csv_uploader: CSVUploader
    ) -> None:
        files = csv_uploader.list_files().files
        preloaded = next(
            (item for item in files if item.stored_path == "data/df_text_by_report.csv"),
            None,
        )
        assert preloaded is not None
        assert preloaded.filename == "df_text_by_report.csv"
        assert preloaded.source == "preloaded"
