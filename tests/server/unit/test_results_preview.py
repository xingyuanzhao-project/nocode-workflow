"""Unit tests for :class:`server.services.results_preview.ResultsPreviewService`.

The service reads the output CSV from the per-run directory. Tests
use the ``summary_csv_fixture_path`` fixture (from conftest) which
copies ``summary.csv`` into ``<run_dir>/summary.csv`` so the service
resolves it naturally.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from server.services.results_preview import ResultsPreviewService


@pytest.fixture
def results_service(server_paths) -> ResultsPreviewService:
    """Build a :class:`ResultsPreviewService` against the isolated paths.

    Returns:
        ResultsPreviewService: Ready-to-use service.
    """
    return ResultsPreviewService(paths=server_paths)


class TestResultsPreviewHappyPath:
    def test_preview_returns_first_n_rows(
        self,
        results_service: ResultsPreviewService,
        summary_csv_fixture_path: Path,
    ) -> None:
        response = results_service.read_preview(
            run_id="preview_fixture_run",
            limit=5,
        )
        assert response.run_id == "preview_fixture_run"
        assert len(response.preview_rows) == 5

    def test_total_row_count_excludes_header(
        self,
        results_service: ResultsPreviewService,
        summary_csv_fixture_path: Path,
    ) -> None:
        response = results_service.read_preview(
            run_id="preview_fixture_run",
            limit=3,
        )
        # Fixture summary.csv has 30 data rows.
        assert response.total_row_count == 30

    def test_columns_preserved_in_order(
        self,
        results_service: ResultsPreviewService,
        summary_csv_fixture_path: Path,
    ) -> None:
        response = results_service.read_preview(
            run_id="preview_fixture_run",
            limit=1,
        )
        assert response.columns == ["entity_id", "summary", "info_found", "row_index"]

    def test_resolve_output_path_returns_absolute(
        self,
        results_service: ResultsPreviewService,
        summary_csv_fixture_path: Path,
    ) -> None:
        resolved = results_service.resolve_output_path("preview_fixture_run")
        assert resolved == summary_csv_fixture_path
        assert resolved.is_absolute()


class TestResultsPreviewErrors:
    def test_missing_output_raises_file_not_found(
        self, results_service: ResultsPreviewService
    ) -> None:
        with pytest.raises(FileNotFoundError):
            results_service.read_preview(
                run_id="nothing_here",
                limit=5,
            )

    def test_negative_limit_rejected(
        self,
        results_service: ResultsPreviewService,
        summary_csv_fixture_path: Path,
    ) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            results_service.read_preview(
                run_id="preview_fixture_run",
                limit=-1,
            )


class TestResultsPreviewNaNHandling:
    def test_nan_cells_become_none(
        self, results_service: ResultsPreviewService, server_paths
    ) -> None:
        run_dir = server_paths.runs_dir / "nan_fixture_run"
        run_dir.mkdir(parents=True, exist_ok=True)
        dataframe = pd.DataFrame({"summary": ["alpha", None, "gamma"]})
        dataframe.to_csv(run_dir / "summary.csv", index=False)
        response = results_service.read_preview(
            run_id="nan_fixture_run",
            limit=10,
        )
        assert response.preview_rows[0]["summary"] == "alpha"
        assert response.preview_rows[1]["summary"] is None
        assert response.preview_rows[2]["summary"] == "gamma"
