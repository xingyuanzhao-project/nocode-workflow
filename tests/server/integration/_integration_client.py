"""HTTP helpers shared by every integration test.

Uses :mod:`httpx` (sync) against the live FastAPI container. Every
helper returns the parsed JSON body or raises
:class:`httpx.HTTPStatusError` on non-2xx.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, Iterable

import httpx


DEFAULT_BASE_URL: str = os.environ.get(
    "AGENT_PAPER_INTEGRATION_BASE_URL", "http://127.0.0.1:8000"
).rstrip("/")


_TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled"})


def request_json(
    method: str,
    path: str,
    *,
    json_body: Dict[str, Any] | None = None,
    base_url: str = DEFAULT_BASE_URL,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """Send an HTTP request and return the parsed JSON body.

    Args:
        method (str): HTTP method (``"GET"``, ``"POST"``, ...).
        path (str): Path starting with ``/``.
        json_body (Dict[str, Any] | None): Optional JSON body.
        base_url (str): Server base URL.
        timeout (float): Request timeout seconds.

    Returns:
        Dict[str, Any]: Parsed JSON body.
    """
    with httpx.Client(base_url=base_url, timeout=timeout) as client:
        response = client.request(method, path, json=json_body)
        response.raise_for_status()
        if response.content:
            return response.json()
        return {}


def upload_csv(
    local_path: Path, *, base_url: str = DEFAULT_BASE_URL
) -> Dict[str, Any]:
    """POST ``local_path`` to ``/api/files/upload``.

    Args:
        local_path (Path): CSV file on disk.
        base_url (str): Server base URL.

    Returns:
        Dict[str, Any]: Parsed :class:`CSVUploadResponse` JSON.
    """
    with httpx.Client(base_url=base_url, timeout=60.0) as client:
        with local_path.open("rb") as file_handle:
            response = client.post(
                "/api/files/upload",
                files={"file": (local_path.name, file_handle, "text/csv")},
            )
        response.raise_for_status()
        return response.json()


def poll_run_until_terminal(
    run_id: str,
    *,
    timeout_seconds: float = 900.0,
    poll_interval_seconds: float = 5.0,
    base_url: str = DEFAULT_BASE_URL,
) -> Dict[str, Any]:
    """Poll ``/api/flow/status/{run_id}`` until a terminal status or timeout.

    Args:
        run_id (str): The run identifier.
        timeout_seconds (float): Hard timeout.
        poll_interval_seconds (float): Sleep between polls.
        base_url (str): Server base URL.

    Returns:
        Dict[str, Any]: Final status DTO.

    Raises:
        TimeoutError: When no terminal status is observed within the
            timeout.
    """
    deadline = time.monotonic() + timeout_seconds
    last_status_dto: Dict[str, Any] = {}
    while time.monotonic() < deadline:
        last_status_dto = request_json(
            "GET", f"/api/flow/status/{run_id}", base_url=base_url
        )
        if last_status_dto.get("status") in _TERMINAL_STATUSES:
            return last_status_dto
        time.sleep(poll_interval_seconds)
    raise TimeoutError(
        f"Run {run_id} did not reach a terminal status within {timeout_seconds}s; "
        f"last seen: {last_status_dto}"
    )


def build_single_summary_flow(
    stored_path: str,
    *,
    model: str = "google/gemini-2.5-flash",
    processing_limit: int = 1,
) -> Dict[str, Any]:
    """Return a one-step single-summary flow bound to ``stored_path``.

    Args:
        stored_path (str): Project-root-relative POSIX path returned
            by :func:`upload_csv`.
        model (str): OpenRouter model id. Defaults to a cheap, fast
            model so the suite stays inexpensive.
        processing_limit (int): How many rows to process.

    Returns:
        Dict[str, Any]: Flow body ready for :func:`submit_adhoc_run`.
    """
    return {
        "schema_version": 1,
        "name": "integration_single_summary",
        "description": "pytest integration: single-summary row flow",
        "resources": [
            {
                "id": "default",
                "type": "llm_provider",
                "provider": "openrouter",
                "model": model,
                "api_base": "https://openrouter.ai/api/v1",
                "api_key_env": "OPENROUTER_API_KEY",
                "temperature": 0.0,
                "max_tokens_summary": 1024,
                "max_tokens_classification": 256,
            }
        ],
        "data": {
            "input_csv": stored_path,
            "column_roles": {
                "text": "text",
                "entity_id": "victim",
                "doc_id": "index",
                "sort_by": "index",
            },
        },
        "taxonomy": "config/taxonomy.json",
        "prompts": "config/prompts.json",
        "steps": [{"type": "single_summary", "unit": "row"}],
        "processing_limit": processing_limit,
        "async": {
            "enabled": True,
            "max_concurrent_rows": 2,
            "max_concurrent_llm_calls": 2,
            "max_retries": 2,
        },
        "output": {"summary_csv": "integration/summary.csv", "extend": False},
        "logging": {"file": "integration/processing.log", "log_progress": True},
        "display": {"use_progress_bar": False},
    }


def build_conversation_summary_flow(
    stored_path: str,
    *,
    model: str = "google/gemini-2.5-flash",
    processing_limit: int = 1,
) -> Dict[str, Any]:
    """Return a two-step conversation-summary flow for entity-unit tests.

    Args:
        stored_path (str): Upload stored_path.
        model (str): OpenRouter model id.
        processing_limit (int): Number of entities to process.

    Returns:
        Dict[str, Any]: Flow body.
    """
    flow = build_single_summary_flow(
        stored_path, model=model, processing_limit=processing_limit
    )
    flow["name"] = "integration_conversation_summary"
    flow["description"] = "pytest integration: conversation-summary entity flow"
    flow["steps"] = [
        {
            "type": "conversation_summary_first",
            "unit": "document",
            "group_by": "entity",
        },
        {
            "type": "conversation_summary_update",
            "unit": "document",
            "group_by": "entity",
        },
    ]
    flow["output"]["results_csv"] = "integration/results.csv"
    flow["output"]["states_csv"] = "integration/states.csv"
    flow["output"]["spans_csv"] = "integration/spans.csv"
    return flow


def submit_adhoc_run(
    flow_body: Dict[str, Any], *, base_url: str = DEFAULT_BASE_URL
) -> str:
    """Submit a flow and return the minted ``run_id``.

    Args:
        flow_body (Dict[str, Any]): Flow body.
        base_url (str): Server base URL.

    Returns:
        str: The newly-minted run id.
    """
    response = request_json(
        "POST", "/api/flow/run", json_body={"flow": flow_body}, base_url=base_url
    )
    return response["run_id"]
