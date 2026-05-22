"""Route tests for ``/api/flow/*``.

Covers full saved-flow CRUD + duplicate, plus the run + resume +
status endpoints with eager Celery.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestFlowCRUD:
    def test_list_then_create_then_list(
        self, test_client: TestClient, valid_flow_body: dict
    ) -> None:
        first_list = test_client.get("/api/flow/list").json()
        assert first_list == []

        create_response = test_client.post(
            "/api/flow", json={"name": "My Flow", "flow": valid_flow_body}
        )
        assert create_response.status_code == 201
        flow_id = create_response.json()["id"]

        listed = test_client.get("/api/flow/list").json()
        assert len(listed) == 1
        assert listed[0]["id"] == flow_id
        assert listed[0]["name"] == "My Flow"

    def test_get_unknown_returns_404(self, test_client: TestClient) -> None:
        response = test_client.get("/api/flow/does_not_exist")
        assert response.status_code == 404

    def test_update_then_get(
        self, test_client: TestClient, valid_flow_body: dict
    ) -> None:
        create_response = test_client.post(
            "/api/flow", json={"name": "Name A", "flow": valid_flow_body}
        )
        flow_id = create_response.json()["id"]

        update_body = {**valid_flow_body, "description": "updated"}
        patch_response = test_client.put(
            f"/api/flow/{flow_id}",
            json={"name": "Name A", "flow": update_body},
        )
        assert patch_response.status_code == 200

        fetched = test_client.get(f"/api/flow/{flow_id}").json()
        assert fetched["flow"]["description"] == "updated"

    def test_duplicate_creates_new_id(
        self, test_client: TestClient, valid_flow_body: dict
    ) -> None:
        create_response = test_client.post(
            "/api/flow", json={"name": "Source", "flow": valid_flow_body}
        )
        source_id = create_response.json()["id"]
        dup_response = test_client.post(
            f"/api/flow/{source_id}/duplicate", json={"new_name": "Source Copy"}
        )
        assert dup_response.status_code == 201
        assert dup_response.json()["id"] != source_id

    def test_delete_removes_flow(
        self, test_client: TestClient, valid_flow_body: dict
    ) -> None:
        create_response = test_client.post(
            "/api/flow", json={"name": "Doomed", "flow": valid_flow_body}
        )
        flow_id = create_response.json()["id"]
        delete_response = test_client.delete(f"/api/flow/{flow_id}")
        assert delete_response.status_code == 204
        assert test_client.get(f"/api/flow/{flow_id}").status_code == 404

    def test_list_reports_not_found_not_five_hundred(
        self, test_client: TestClient
    ) -> None:
        response = test_client.delete("/api/flow/never_existed")
        assert response.status_code == 404


class TestFlowRun:
    def test_run_adhoc_enqueues_task_and_reports_queued(
        self,
        test_client: TestClient,
        valid_flow_body: dict,
        monkeypatch,
    ) -> None:
        # Prevent the eager Celery worker from importing the real task
        # body (which would hit OpenRouter) by replacing send_task.
        calls = []

        def _recorded_send_task(name, args=None, kwargs=None, **_extra):
            calls.append({"name": name, "args": list(args or [])})

        monkeypatch.setattr(
            test_client.app.state.celery_app, "send_task", _recorded_send_task
        )

        response = test_client.post(
            "/api/flow/run", json={"flow": valid_flow_body}
        )
        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "queued"
        assert body["run_id"]
        assert len(calls) == 1
        assert calls[0]["args"] == [body["run_id"]]

    def test_run_saved_flow_enqueues_task(
        self,
        test_client: TestClient,
        valid_flow_body: dict,
        monkeypatch,
    ) -> None:
        calls = []
        monkeypatch.setattr(
            test_client.app.state.celery_app,
            "send_task",
            lambda name, args=None, **_: calls.append(args[0]),
        )
        create_response = test_client.post(
            "/api/flow", json={"name": "Saved Run Flow", "flow": valid_flow_body}
        )
        flow_id = create_response.json()["id"]
        run_response = test_client.post(f"/api/flow/{flow_id}/run")
        assert run_response.status_code == 202
        assert calls == [run_response.json()["run_id"]]

    def test_resume_unknown_run_returns_404(
        self, test_client: TestClient
    ) -> None:
        response = test_client.post("/api/flow/resume/unknown")
        assert response.status_code == 404

    def test_status_unknown_returns_404(
        self, test_client: TestClient
    ) -> None:
        response = test_client.get("/api/flow/status/unknown")
        assert response.status_code == 404

    def test_status_after_submit_reports_queued(
        self,
        test_client: TestClient,
        valid_flow_body: dict,
        monkeypatch,
    ) -> None:
        monkeypatch.setattr(
            test_client.app.state.celery_app, "send_task", lambda *a, **k: None
        )
        submit_response = test_client.post(
            "/api/flow/run", json={"flow": valid_flow_body}
        )
        run_id = submit_response.json()["run_id"]
        status_response = test_client.get(f"/api/flow/status/{run_id}")
        assert status_response.status_code == 200
        assert status_response.json()["status"] == "queued"
