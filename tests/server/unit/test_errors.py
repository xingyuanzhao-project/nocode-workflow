"""Unit tests for :mod:`server.errors`.

The installer maps four Python exception types to four HTTP status
codes. A small FastAPI app with one route per exception type lets us
assert the mapping without pulling in the real service layer.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from server.errors import install_exception_handlers


class _InnerModel(BaseModel):
    required_field: str


@pytest.fixture
def error_probe_app() -> FastAPI:
    """Return a FastAPI app whose four routes raise the four exception types.

    The test client hits each route and asserts the installed handler
    translated the exception into the expected status + body shape.
    """
    app = FastAPI()
    install_exception_handlers(app)

    @app.get("/raise_not_found")
    def _raise_not_found() -> Any:
        raise FileNotFoundError("missing.csv")

    @app.get("/raise_value_error")
    def _raise_value_error() -> Any:
        raise ValueError("bad input")

    @app.get("/raise_permission_error")
    def _raise_permission_error() -> Any:
        raise PermissionError("nope")

    @app.get("/raise_validation_error")
    def _raise_validation_error() -> Any:
        try:
            _InnerModel()  # missing required_field
        except ValidationError as exc:
            raise exc
        return {}

    return app


class TestErrorHandlers:
    @pytest.mark.parametrize(
        "path, expected_status, expected_type",
        [
            ("/raise_not_found", 404, "not_found"),
            ("/raise_value_error", 400, "value_error"),
            ("/raise_permission_error", 403, "forbidden"),
        ],
    )
    def test_simple_exceptions_map_to_status(
        self,
        error_probe_app: FastAPI,
        path: str,
        expected_status: int,
        expected_type: str,
    ) -> None:
        with TestClient(error_probe_app) as client:
            response = client.get(path)
        assert response.status_code == expected_status
        body = response.json()
        assert body["errors"][0]["type"] == expected_type
        assert isinstance(body["errors"][0]["msg"], str)

    def test_validation_error_maps_to_422(self, error_probe_app: FastAPI) -> None:
        with TestClient(error_probe_app) as client:
            response = client.get("/raise_validation_error")
        assert response.status_code == 422
        body = response.json()
        assert body["errors"]
        assert body["errors"][0]["loc"] == ["required_field"]
