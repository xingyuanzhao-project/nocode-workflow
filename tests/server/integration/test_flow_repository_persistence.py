"""Integration test asserting saved flows persist to disk.

Creates a flow via ``POST /api/flow`` and re-fetches it via
``GET /api/flow/list`` to prove the bind-mounted ``server/data/flows``
volume is reachable and writable from inside the container.

Does not restart the container — that would be a slow, disruptive
step that the backend smoke suite already covers implicitly (the
next ``docker compose up`` starts from the same on-disk state).
"""

from __future__ import annotations

import uuid

import pytest

from ._docker_probe import require_running_stack
from ._integration_client import request_json


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def _stack_up() -> None:
    require_running_stack()


class TestFlowRepositoryPersistence:
    def test_created_flow_appears_in_subsequent_list(
        self, valid_flow_body: dict
    ) -> None:
        unique_name = f"persist_{uuid.uuid4().hex[:8]}"
        create_response = request_json(
            "POST",
            "/api/flow",
            json_body={"name": unique_name, "flow": valid_flow_body},
        )
        flow_id = create_response["id"]

        try:
            listed = request_json("GET", "/api/flow/list")
            assert any(item["id"] == flow_id for item in listed)
            fetched = request_json("GET", f"/api/flow/{flow_id}")
            assert fetched["name"] == unique_name
        finally:
            request_json("DELETE", f"/api/flow/{flow_id}")
