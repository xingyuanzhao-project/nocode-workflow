"""End-to-end smoke test for the academic_pipeline Phase 2 backend.

Exercises the full contract a real client would use::

    /api/health                              -> redis_ok and worker_ok
    /api/files/upload                        -> stored_path
    /api/schema/validate                     -> accepts the flow
    /api/flow/run                            -> enqueues a run
    /api/flow/status/{run_id}                -> polled to success
    /api/flow/runs/{run_id}/preview          -> first rows of summary.csv
    /api/flow/runs/{run_id}/output           -> streamed CSV download
    /api/flow/runs/{run_id}/logs/stream      -> SSE log relay (second run)

Expected environment
--------------------

The docker-compose stack at the repository root must be running with
all three services healthy (``redis``, ``web``, ``celery_worker``).
The OpenRouter API key used by the built-in smoke flow lives in the
project-root ``.env`` as ``OPENROUTER_API_KEY``; the worker picks it
up via :func:`src.flow_builder._load_dotenv_into_environ` at task
start time.

Invocation
----------

Run from the project root::

    python scripts/smoke_test_backend.py

The script uses only the Python standard library and therefore works
from the project ``.venv`` or from any plain interpreter.

Environment overrides
---------------------

- ``ACADEMIC_PIPELINE_SMOKE_BASE_URL``: HTTP base URL (default
  ``http://127.0.0.1:8000``).
- ``ACADEMIC_PIPELINE_SMOKE_CSV``: Path to the CSV to upload, resolved
  relative to the current working directory. Default
  ``data/df_text_by_report.csv``.
- ``ACADEMIC_PIPELINE_SMOKE_PROCESSING_LIMIT``: ``processing_limit`` value
  used in the main flow (default ``1``).
- ``ACADEMIC_PIPELINE_SMOKE_POLL_TIMEOUT_SECONDS``: Poll timeout in seconds
  (default ``600``).
- ``ACADEMIC_PIPELINE_SMOKE_POLL_INTERVAL_SECONDS``: Poll interval in
  seconds (default ``5``).
- ``ACADEMIC_PIPELINE_SMOKE_SSE_TIMEOUT_SECONDS``: Hard timeout on the SSE
  stream read stage (default ``180``).

Exit codes
----------

``0`` on success. Any non-zero exit code indicates a failed stage;
the offending stage name is printed to stderr.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, Optional

_DEFAULT_BASE_URL: str = "http://127.0.0.1:8000"
_DEFAULT_CSV_PATH: str = "data/df_text_by_report.csv"
_DEFAULT_PROCESSING_LIMIT: int = 1
_DEFAULT_POLL_TIMEOUT_SECONDS: int = 600
_DEFAULT_POLL_INTERVAL_SECONDS: int = 5
_DEFAULT_SSE_TIMEOUT_SECONDS: int = 180
_DEFAULT_PREVIEW_ROW_LIMIT: int = 5

_TERMINAL_RUN_STATUSES: frozenset[str] = frozenset({"succeeded", "failed", "cancelled"})
"""Run statuses after which no further transitions are expected."""


def _read_env(variable_name: str, default_value: str) -> str:
    """Return ``os.environ[variable_name]`` if set, else ``default_value``.

    Args:
        variable_name (str): Environment variable to read.
        default_value (str): Fallback when the variable is unset or empty.

    Returns:
        str: The resolved value.
    """
    raw_value = os.environ.get(variable_name, "").strip()
    return raw_value if raw_value else default_value


def _read_env_int(variable_name: str, default_value: int) -> int:
    """Return ``os.environ[variable_name]`` coerced to ``int``.

    Args:
        variable_name (str): Environment variable to read.
        default_value (int): Fallback when the variable is unset or empty.

    Returns:
        int: The parsed integer value.

    Raises:
        ValueError: If the environment value is set but not an integer.
    """
    raw_value = os.environ.get(variable_name, "").strip()
    if not raw_value:
        return default_value
    return int(raw_value)


def _request_json(
    method: str,
    base_url: str,
    path: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Send an HTTP request with a JSON body and decode the JSON response.

    Args:
        method (str): HTTP method (``"GET"``, ``"POST"``).
        base_url (str): Base URL without a trailing slash.
        path (str): Request path starting with ``/``.
        payload (Optional[Dict[str, Any]]): Body to serialise as JSON.

    Returns:
        Dict[str, Any]: Parsed JSON body.

    Raises:
        urllib.error.HTTPError: If the response status is non-2xx.
    """
    encoded_body: Optional[bytes] = None
    headers: Dict[str, str] = {}
    if payload is not None:
        encoded_body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=encoded_body,
        headers=headers,
        method=method,
    )
    with urllib.request.urlopen(request) as response:
        response_body = response.read()
    return json.loads(response_body) if response_body else {}


def _upload_csv(base_url: str, csv_path: pathlib.Path) -> Dict[str, Any]:
    """POST ``csv_path`` to ``/api/files/upload`` as ``multipart/form-data``.

    The multipart body is constructed by hand so the script avoids a
    third-party dependency.

    Args:
        base_url (str): Backend base URL.
        csv_path (pathlib.Path): Local CSV file to upload.

    Returns:
        Dict[str, Any]: Parsed :class:`server.schemas.files.CSVUploadResponse`.

    Raises:
        FileNotFoundError: If ``csv_path`` does not exist.
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found at {csv_path}")
    boundary = f"----academic_pipeline_smoke_{uuid.uuid4().hex}"
    content_bytes = csv_path.read_bytes()
    body = b"".join(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            (
                f'Content-Disposition: form-data; name="file"; '
                f'filename="{csv_path.name}"\r\n'
                f"Content-Type: text/csv\r\n\r\n"
            ).encode("utf-8"),
            content_bytes,
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    request = urllib.request.Request(
        f"{base_url}/api/files/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())


def _build_smoke_flow(
    stored_path: str, processing_limit: int
) -> Dict[str, Any]:
    """Build a minimal two-step conversation-summary flow in node-edge format.

    The flow references the uploaded CSV via ``stored_path`` (which is
    project-root-relative POSIX) and caps work at ``processing_limit``
    entities so the smoke test completes quickly while still exercising
    the full runner loop.

    Args:
        stored_path (str): Value of
            :attr:`server.schemas.files.CSVUploadResponse.stored_path`
            returned by the upload endpoint.
        processing_limit (int): Number of entities to process.

    Returns:
        Dict[str, Any]: A flow body valid under
        :class:`src.flow_loader.FlowDocument`.
    """
    return {
        "name": "smoke_test_backend",
        "description": "End-to-end smoke test: upload -> validate -> run",
        "nodes": [
            {
                "id": "input_1",
                "type": "csv_input",
                "config": {
                    "selected_file": stored_path,
                },
            },
            {
                "id": "proc_summary_first",
                "type": "processor",
                "config": {
                    "step_type": "conversation_summary_first",
                    "unit": "document",
                    "group_by": "entity",
                },
            },
            {
                "id": "proc_summary_update",
                "type": "processor",
                "config": {
                    "step_type": "conversation_summary_update",
                    "unit": "document",
                    "group_by": "entity",
                },
            },
            {
                "id": "llm_1",
                "type": "llm_call",
                "config": {
                    "resource_id": "default",
                    "provider": "openrouter",
                    "model": "google/gemini-2.5-pro",
                    "api_base": "https://openrouter.ai/api/v1",
                    "api_key_env": "OPENROUTER_API_KEY",
                    "temperature": 0.0,
                    "max_tokens": 8192,
                },
            },
            {
                "id": "codebook_1",
                "type": "codebook",
                "config": {
                    "codebook_path": "config/taxonomy.json",
                },
            },
            {
                "id": "output_1",
                "type": "csv_output",
                "config": {
                    "output_path": "summary.csv",
                    "extend": False,
                },
            },
        ],
        "edges": [
            {"type": "feedforward", "source": "input_1", "target": "proc_summary_first"},
            {"type": "feedforward", "source": "proc_summary_first", "target": "proc_summary_update"},
            {"type": "feedforward", "source": "proc_summary_update", "target": "output_1"},
            {"type": "llm_call", "source": "proc_summary_first", "target": "llm_1"},
            {"type": "llm_call", "source": "proc_summary_update", "target": "llm_1"},
            {"type": "codebook_inquiry", "source": "proc_summary_first", "target": "codebook_1"},
        ],
        "settings": {
            "processing_limit": processing_limit,
            "async": {
                "enabled": True,
                "max_concurrent_rows": 2,
                "max_concurrent_llm_calls": 4,
                "max_retries": 3,
            },
            "logging": {
                "file": "processing.log",
                "log_progress": True,
                "log_prompts": False,
                "log_response": False,
            },
            "display": {"use_progress_bar": False},
            "prompts": "config/prompts.json",
        },
    }


def _download_output(base_url: str, run_id: str) -> bytes:
    """Download a run's output CSV as raw bytes.

    Args:
        base_url (str): Backend base URL.
        run_id (str): Run identifier.

    Returns:
        bytes: Raw CSV bytes from the response body.

    Raises:
        urllib.error.HTTPError: If the response status is non-2xx.
    """
    request = urllib.request.Request(
        f"{base_url}/api/flow/runs/{run_id}/output",
        method="GET",
    )
    with urllib.request.urlopen(request) as response:
        return response.read()


def _read_log_stream_until_terminal(
    base_url: str, run_id: str, timeout_seconds: int
) -> Dict[str, Any]:
    """Subscribe to the SSE log stream and return a summary of what arrived.

    The function reads the ``text/event-stream`` body one line at a
    time, accumulating each event into a small state machine until
    either a ``status`` event is seen (terminal) or the hard timeout
    fires.

    Args:
        base_url (str): Backend base URL.
        run_id (str): Run identifier to stream.
        timeout_seconds (int): Maximum time to wait for a terminal
            event.

    Returns:
        Dict[str, Any]: Summary with keys ``log_event_count`` (int),
        ``first_log_line`` (Optional[str]; first ``event: log`` payload
        received), ``terminal_status`` (Optional[str]; ``data`` value
        of the ``event: status`` line), and ``elapsed_seconds`` (float).

    Raises:
        TimeoutError: If no terminal ``status`` event arrives within
            ``timeout_seconds``.
    """
    start_monotonic = time.monotonic()
    request = urllib.request.Request(
        f"{base_url}/api/flow/runs/{run_id}/logs/stream",
        headers={"Accept": "text/event-stream"},
        method="GET",
    )
    log_event_count = 0
    first_log_line: Optional[str] = None
    terminal_status: Optional[str] = None
    current_event_name: Optional[str] = None
    current_data_buffer: list[str] = []

    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        while True:
            if time.monotonic() - start_monotonic > timeout_seconds:
                raise TimeoutError(
                    f"SSE stream for run {run_id} did not emit a terminal "
                    f"status event within {timeout_seconds}s"
                )
            raw_line = response.readline()
            if not raw_line:
                break
            decoded_line = raw_line.decode("utf-8").rstrip("\r\n")
            if decoded_line == "":
                if current_event_name == "log":
                    log_event_count += 1
                    joined_data = "\n".join(current_data_buffer)
                    if first_log_line is None:
                        first_log_line = joined_data
                elif current_event_name == "status":
                    terminal_status = "\n".join(current_data_buffer) or None
                    current_event_name = None
                    current_data_buffer = []
                    break
                current_event_name = None
                current_data_buffer = []
                continue
            if decoded_line.startswith(":"):
                continue
            if decoded_line.startswith("event:"):
                current_event_name = decoded_line[len("event:") :].strip()
            elif decoded_line.startswith("data:"):
                current_data_buffer.append(decoded_line[len("data:") :].lstrip())

    if terminal_status is None:
        raise TimeoutError(
            f"SSE stream for run {run_id} closed before emitting a "
            f"terminal status event (received {log_event_count} log events)"
        )
    return {
        "log_event_count": log_event_count,
        "first_log_line": first_log_line,
        "terminal_status": terminal_status,
        "elapsed_seconds": time.monotonic() - start_monotonic,
    }


def _poll_run_until_terminal(
    base_url: str,
    run_id: str,
    poll_interval_seconds: int,
    poll_timeout_seconds: int,
) -> Dict[str, Any]:
    """Poll ``/api/flow/status/{run_id}`` until a terminal status or timeout.

    Args:
        base_url (str): Backend base URL.
        run_id (str): Run identifier returned by ``/api/flow/run``.
        poll_interval_seconds (int): Sleep between polls.
        poll_timeout_seconds (int): Hard timeout.

    Returns:
        Dict[str, Any]: The final status DTO once a terminal status is
        seen.

    Raises:
        TimeoutError: If no terminal status is seen within
            ``poll_timeout_seconds``.
    """
    deadline = time.monotonic() + poll_timeout_seconds
    last_status_line = ""
    while time.monotonic() < deadline:
        status_dto = _request_json("GET", base_url, f"/api/flow/status/{run_id}")
        current_status = status_dto.get("status", "unknown")
        completed_count = status_dto.get("completed_entity_count")
        status_line = f"status={current_status} completed_entity_count={completed_count}"
        if status_line != last_status_line:
            print(f"  {status_line}", flush=True)
            last_status_line = status_line
        if current_status in _TERMINAL_RUN_STATUSES:
            return status_dto
        time.sleep(poll_interval_seconds)
    raise TimeoutError(
        f"run {run_id} did not reach a terminal status within "
        f"{poll_timeout_seconds}s (last status: {last_status_line})"
    )


def _run_smoke_test() -> None:
    """Execute every stage in order, failing fast on the first error."""
    base_url = _read_env(
        "ACADEMIC_PIPELINE_SMOKE_BASE_URL", _DEFAULT_BASE_URL
    ).rstrip("/")
    csv_path = pathlib.Path(
        _read_env("ACADEMIC_PIPELINE_SMOKE_CSV", _DEFAULT_CSV_PATH)
    )
    processing_limit = _read_env_int(
        "ACADEMIC_PIPELINE_SMOKE_PROCESSING_LIMIT", _DEFAULT_PROCESSING_LIMIT
    )
    poll_timeout_seconds = _read_env_int(
        "ACADEMIC_PIPELINE_SMOKE_POLL_TIMEOUT_SECONDS", _DEFAULT_POLL_TIMEOUT_SECONDS
    )
    poll_interval_seconds = _read_env_int(
        "ACADEMIC_PIPELINE_SMOKE_POLL_INTERVAL_SECONDS", _DEFAULT_POLL_INTERVAL_SECONDS
    )
    sse_timeout_seconds = _read_env_int(
        "ACADEMIC_PIPELINE_SMOKE_SSE_TIMEOUT_SECONDS", _DEFAULT_SSE_TIMEOUT_SECONDS
    )

    print(f"[config] base_url={base_url}")
    print(f"[config] csv_path={csv_path}")
    print(f"[config] processing_limit={processing_limit}")
    print(f"[config] poll_timeout_seconds={poll_timeout_seconds}")
    print(f"[config] poll_interval_seconds={poll_interval_seconds}")
    print(f"[config] sse_timeout_seconds={sse_timeout_seconds}")

    print("[1/7] health")
    health_dto = _request_json("GET", base_url, "/api/health")
    print(f"  {health_dto}")
    if not (health_dto.get("redis_ok") and health_dto.get("worker_ok")):
        raise RuntimeError(f"backend not healthy: {health_dto}")

    print("[2/7] upload")
    upload_dto = _upload_csv(base_url, csv_path)
    print(
        f"  upload_id={upload_dto['upload_id']} "
        f"stored_path={upload_dto['stored_path']} "
        f"row_count={upload_dto['row_count']}"
    )

    print("[3/7] validate")
    flow_definition = _build_smoke_flow(upload_dto["stored_path"], processing_limit)
    validation_dto = _request_json(
        "POST", base_url, "/api/schema/validate", {"flow": flow_definition}
    )
    if not validation_dto.get("valid"):
        raise RuntimeError(f"flow failed validation: {validation_dto}")
    print("  valid=True")

    print("[4/7] run")
    start_dto = _request_json(
        "POST", base_url, "/api/flow/run", {"flow": flow_definition}
    )
    run_id = start_dto["run_id"]
    print(f"  run_id={run_id} initial_status={start_dto['status']}")

    print("[5/7] poll")
    final_status_dto = _poll_run_until_terminal(
        base_url,
        run_id,
        poll_interval_seconds,
        poll_timeout_seconds,
    )
    print(f"  final={final_status_dto}")

    if final_status_dto["status"] != "succeeded":
        raise RuntimeError(
            f"run did not succeed: status={final_status_dto['status']} "
            f"error={final_status_dto.get('error_message')}"
        )

    print("[6/7] preview+download")
    preview_dto = _request_json(
        "GET",
        base_url,
        f"/api/flow/runs/{run_id}/preview"
        f"?limit={_DEFAULT_PREVIEW_ROW_LIMIT}",
    )
    preview_row_count = len(preview_dto.get("preview_rows", []))
    total_row_count = preview_dto.get("total_row_count", 0)
    preview_columns = preview_dto.get("columns", [])
    print(
        f"  preview columns={len(preview_columns)} "
        f"preview_rows={preview_row_count} "
        f"total_rows={total_row_count}"
    )
    if total_row_count < 1 or preview_row_count < 1:
        raise RuntimeError(
            f"preview returned no rows: total_row_count={total_row_count}, "
            f"preview_rows={preview_row_count}"
        )
    summary_bytes = _download_output(base_url, run_id)
    print(f"  summary.csv downloaded ({len(summary_bytes)} bytes)")
    if len(summary_bytes) < len(",".join(preview_columns)):
        raise RuntimeError(
            f"summary.csv download is suspiciously short "
            f"({len(summary_bytes)} bytes)"
        )

    print("[7/7] sse")
    sse_start_dto = _request_json(
        "POST", base_url, "/api/flow/run", {"flow": flow_definition}
    )
    sse_run_id = sse_start_dto["run_id"]
    print(f"  sse_run_id={sse_run_id}")
    sse_summary = _read_log_stream_until_terminal(
        base_url, sse_run_id, sse_timeout_seconds
    )
    print(
        f"  log_event_count={sse_summary['log_event_count']} "
        f"terminal_status={sse_summary['terminal_status']} "
        f"elapsed_seconds={sse_summary['elapsed_seconds']:.1f}"
    )
    if sse_summary["log_event_count"] < 1:
        raise RuntimeError(
            f"SSE stream for run {sse_run_id} delivered no log events "
            "before the terminal status; worker Redis publisher may be "
            "misconfigured"
        )
    if sse_summary["terminal_status"] != "succeeded":
        raise RuntimeError(
            f"SSE second run did not succeed: "
            f"terminal_status={sse_summary['terminal_status']}"
        )

    print("[done] smoke test passed")


if __name__ == "__main__":
    try:
        _run_smoke_test()
    except Exception as exc:
        print(f"[fail] {exc.__class__.__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
