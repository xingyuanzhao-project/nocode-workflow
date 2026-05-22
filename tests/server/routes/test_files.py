"""Route tests for ``POST /api/files/upload``."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient


class TestFilesUpload:
    def test_accepts_valid_csv(
        self, test_client: TestClient, tiny_csv_bytes: bytes
    ) -> None:
        response = test_client.post(
            "/api/files/upload",
            files={"file": ("tiny.csv", io.BytesIO(tiny_csv_bytes), "text/csv")},
        )
        # The upload endpoint reports 201 Created with the stored_path
        # in the body.
        assert response.status_code in (200, 201)
        body = response.json()
        assert body["filename"] == "tiny.csv"
        assert body["row_count"] == 5
        assert body["stored_path"].startswith("server/data/")
        assert body["stored_path"].endswith(".csv")

    def test_oversize_returns_400(
        self,
        test_client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            test_client.app.state.csv_uploader.settings, "max_upload_bytes", 10
        )
        oversized = b"text,victim,index\n" + b"a,b,c\n" * 50
        response = test_client.post(
            "/api/files/upload",
            files={"file": ("big.csv", io.BytesIO(oversized), "text/csv")},
        )
        assert response.status_code == 400

    def test_malformed_payload_returns_400(
        self, test_client: TestClient
    ) -> None:
        response = test_client.post(
            "/api/files/upload",
            files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
        )
        assert response.status_code == 400
