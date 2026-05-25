"""Shared fixtures for the :mod:`tests` test suite.

Every service, route, and integration test is built on the same small
set of fixtures declared here. They fall into four groups:

1. **Settings and paths** — :func:`isolated_server_settings`,
   :func:`server_paths`. A fresh ``server/data/…`` directory inside a
   ``tmp_path`` (still under the project root so
   :func:`server.storage.paths._project_root_relative_posix` stays
   valid) is created per test.
2. **Redis doubles** — :func:`fake_redis_client`,
   :func:`patch_build_redis_client`. fakeredis replaces every
   production client so tests never touch a real server.
3. **Celery doubles** — :func:`eager_celery_app` with
   ``task_always_eager = True``, so ``send_task`` runs the task body
   inline.
4. **FastAPI app** — :func:`test_client` wires 1 + 2 + 3 together and
   yields a :class:`fastapi.testclient.TestClient`.

A handful of utility fixtures load YAML / CSV / JSON from
:mod:`tests.fixtures` so the test bodies stay focused.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List

import fakeredis
import pytest
import yaml
from celery import Celery
from fastapi.testclient import TestClient


_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
"""Absolute path of the project root (the parent of ``tests/``)."""


_FIXTURES_DIR: Path = Path(__file__).resolve().parent / "fixtures"
"""Directory holding the YAML/CSV/JSON fixtures shared across tests."""


# Ensure the project root is importable (``src`` and ``server`` sit
# under it) when pytest is invoked from an odd working directory.
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


@pytest.fixture
def project_root() -> Path:
    """Return the absolute project root path.

    Returns:
        Path: ``<repo>``.
    """
    return _PROJECT_ROOT


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the absolute path of the on-disk fixtures directory.

    Returns:
        Path: ``tests/fixtures``.
    """
    return _FIXTURES_DIR


@pytest.fixture
def isolated_data_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a per-test ``data_dir`` under the project root.

    :func:`server.storage.paths._project_root_relative_posix` requires
    the data directory to lie *inside* the project root. A plain
    ``tmp_path`` typically resolves to ``%TEMP%``, which is outside the
    repo; we instead create a unique subdirectory of ``server/data`` so
    every test has a fresh, sandboxed workspace.

    Args:
        tmp_path_factory (pytest.TempPathFactory): pytest tmp-path
            factory used to mint a unique suffix.

    Yields:
        Path: Absolute path of the fresh data directory.
    """
    suffix = tmp_path_factory.mktemp("pytest_data").name
    data_dir = _PROJECT_ROOT / "server" / f"test_{suffix}"
    data_dir.mkdir(parents=True, exist_ok=True)
    yield data_dir
    _remove_tree(data_dir)


def _remove_tree(target: Path) -> None:
    """Remove ``target`` recursively, tolerating already-deleted paths.

    Args:
        target (Path): Directory to remove.

    Returns:
        None.
    """
    if not target.exists():
        return
    for child in target.iterdir():
        if child.is_dir():
            _remove_tree(child)
        else:
            try:
                child.unlink()
            except FileNotFoundError:
                continue
    try:
        target.rmdir()
    except OSError:
        pass


@pytest.fixture
def isolated_server_settings(
    isolated_data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Return a :class:`server.settings.ServerSettings` pinned to an isolated data dir.

    Clears the :func:`server.settings.get_settings` LRU cache so the
    freshly-built settings replace the process-wide default for the
    duration of the test.

    Args:
        isolated_data_dir (Path): From :func:`isolated_data_dir`.
        monkeypatch (pytest.MonkeyPatch): Used to set environment
            overrides that ``ServerSettings`` picks up.

    Yields:
        ServerSettings: The isolated settings instance.
    """
    from server.settings import ServerSettings, get_settings

    monkeypatch.setenv("ACADEMIC_PIPELINE_SERVER_ROOT", str(isolated_data_dir))
    # Keep the real Redis URL out of tests so nothing accidentally
    # connects to a production instance via get_settings().
    monkeypatch.setenv("ACADEMIC_PIPELINE_REDIS_URL", "redis://fakeredis.invalid:6379")
    monkeypatch.setenv("ACADEMIC_PIPELINE_REDIS_KEY_PREFIX", "academic_pipeline_test")
    get_settings.cache_clear()
    settings = ServerSettings()
    yield settings
    get_settings.cache_clear()


@pytest.fixture
def server_paths(isolated_server_settings):
    """Return a :class:`ServerPaths` built from :func:`isolated_server_settings`.

    Args:
        isolated_server_settings: The isolated settings instance.

    Returns:
        ServerPaths: Directory layout rooted at the isolated data dir.
    """
    from server.storage.paths import ServerPaths

    return ServerPaths.from_settings(isolated_server_settings)


@pytest.fixture
def fake_redis_client() -> "fakeredis.FakeRedis":
    """Return a fresh :class:`fakeredis.FakeRedis` with ``decode_responses=True``.

    Every test gets its own in-memory Redis so state never leaks.

    Returns:
        fakeredis.FakeRedis: A decoded-string client.
    """
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def patch_build_redis_client(
    fake_redis_client: "fakeredis.FakeRedis",
    monkeypatch: pytest.MonkeyPatch,
) -> "fakeredis.FakeRedis":
    """Redirect every caller of :func:`build_redis_client` to one fakeredis instance.

    Both the sync :mod:`server.redis_client` module and the
    :class:`server.services.run_registry.RunRegistry` build their own
    ``redis.Redis`` clients. Tests want them all to share one fakeredis
    instance so published messages and hash mutations are visible across
    services.

    Every module that did ``from server.redis_client import
    build_redis_client`` now holds its own local binding, so patching
    only the source module is not enough — we also patch every
    downstream local binding so the fakeredis instance wins no matter
    how the service module acquired its reference.

    Args:
        fake_redis_client (fakeredis.FakeRedis): The shared in-memory
            Redis instance.
        monkeypatch (pytest.MonkeyPatch): Used to swap module globals.

    Returns:
        fakeredis.FakeRedis: Same as ``fake_redis_client``; returned for
        convenience so test bodies do not have to request both.
    """
    from server import app as app_module
    from server import redis_client as redis_client_module
    from server.routes import health as health_route_module
    from server.services import run_registry as run_registry_module

    def _build_client(_base_redis_url: str, _db_index: int) -> "fakeredis.FakeRedis":
        return fake_redis_client

    monkeypatch.setattr(redis_client_module, "build_redis_client", _build_client)
    monkeypatch.setattr(run_registry_module, "build_redis_client", _build_client)
    monkeypatch.setattr(health_route_module, "build_redis_client", _build_client)
    monkeypatch.setattr(app_module, "build_redis_client", _build_client)
    return fake_redis_client


@pytest.fixture
def eager_celery_app() -> Celery:
    """Return a :class:`celery.Celery` in eager mode.

    ``task_always_eager=True`` makes :meth:`Celery.send_task` run the
    target task body inline, synchronously, in the calling thread.
    ``task_eager_propagates=True`` surfaces task exceptions as test
    failures instead of swallowing them.

    Returns:
        Celery: Eager-mode Celery application.
    """
    application = Celery("academic_pipeline_tests")
    application.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
        broker_url="memory://",
        result_backend="cache+memory://",
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
    )
    return application


@pytest.fixture
def recorded_celery_app(monkeypatch: pytest.MonkeyPatch):
    """Return a Celery stand-in that records :meth:`send_task` calls.

    Route tests that care about *what* was enqueued, not *that* the
    task actually ran, use this instead of :func:`eager_celery_app`.

    Args:
        monkeypatch (pytest.MonkeyPatch): Unused today; requested so the
            fixture matches the signature of the eager variant.

    Returns:
        object: A lightweight stand-in exposing
        ``send_task(name, args=None, kwargs=None)`` and a
        ``calls: list[dict]`` attribute recording every invocation.
    """

    class _RecordedCeleryApp:
        def __init__(self) -> None:
            self.calls: List[Dict[str, Any]] = []
            self.control = _RecordedControl()

        def send_task(self, name, args=None, kwargs=None, **extra):
            self.calls.append(
                {"name": name, "args": list(args or []), "kwargs": dict(kwargs or {})}
            )

    class _RecordedControl:
        def inspect(self, timeout=None):
            return _RecordedInspect()

    class _RecordedInspect:
        def ping(self):
            return {"celery@test": {"ok": "pong"}}

    return _RecordedCeleryApp()


@pytest.fixture
def test_client(
    isolated_server_settings,
    server_paths,
    patch_build_redis_client,
    eager_celery_app: Celery,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    """Build a :class:`TestClient` wired to the isolated fixtures.

    Replaces the process-wide :data:`server.celery_app.celery_app`
    with :func:`eager_celery_app` so the web process and anything that
    reads ``app.state.celery_app`` share the eager instance. Also
    patches :mod:`server.redis_client` via
    :func:`patch_build_redis_client`.

    Yields:
        TestClient: A ready-to-use FastAPI test client.
    """
    from server import app as server_app_module
    from server import celery_app as celery_module

    monkeypatch.setattr(celery_module, "celery_app", eager_celery_app)
    monkeypatch.setattr(server_app_module, "celery_app", eager_celery_app)

    application = server_app_module.create_app()
    # Overwrite the celery instance stashed on app.state: ``create_app``
    # already set it before the monkeypatch took effect if import order
    # cached it.
    application.state.celery_app = eager_celery_app

    with TestClient(application) as client:
        yield client


@pytest.fixture
def flow_validator():
    """Return a fresh :class:`FlowValidator`.

    Returns:
        FlowValidator: Fresh instance; no state to share.
    """
    from server.services.flow_validation import FlowValidator

    return FlowValidator()


@pytest.fixture
def valid_flow_body(fixtures_dir: Path) -> Dict[str, Any]:
    """Return a minimal valid FlowDocument-shaped body for validation tests.

    Returns:
        Dict[str, Any]: Raw flow body ready to pass to a validator or
        the ``/api/schema/validate`` endpoint.
    """
    return {
        "name": "fixture_conversation_summary",
        "description": "Valid fixture for the pytest suite.",
        "nodes": [
            {
                "id": "input_1",
                "type": "csv_input",
                "config": {"selected_file": "data/df_text_by_report.csv"},
            },
            {
                "id": "proc_first",
                "type": "processor",
                "config": {
                    "processor_type": "conversation_summary_first",
                    "unit": "document",
                    "group_by": "entity",
                },
            },
            {
                "id": "proc_update",
                "type": "processor",
                "config": {
                    "processor_type": "conversation_summary_update",
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
                    "model": "meta-llama/llama-3.1-70b-instruct",
                    "api_base": "https://openrouter.ai/api/v1",
                    "api_key_env": "OPENROUTER_API_KEY",
                    "temperature": 0.0,
                    "max_tokens": 1024,
                },
            },
            {
                "id": "codebook_1",
                "type": "codebook",
                "config": {"codebook_path": "config/taxonomy.json"},
            },
            {
                "id": "output_1",
                "type": "csv_output",
                "config": {
                    "output_path": "results/fixture/summary.csv",
                    "extend": False,
                },
            },
        ],
        "edges": [
            {"type": "feedforward", "source": "input_1", "target": "proc_first"},
            {"type": "feedforward", "source": "proc_first", "target": "proc_update"},
            {"type": "feedforward", "source": "proc_update", "target": "output_1"},
            {"type": "llm_call", "source": "proc_first", "target": "llm_1"},
            {"type": "llm_call", "source": "proc_update", "target": "llm_1"},
            {"type": "codebook_inquiry", "source": "proc_first", "target": "codebook_1"},
        ],
        "settings": {
            "processing_limit": None,
            "async": {
                "enabled": True,
                "max_concurrent_rows": 2,
                "max_concurrent_llm_calls": 4,
                "max_retries": 3,
            },
            "logging": {
                "file": "results/fixture/processing.log",
                "log_progress": True,
                "log_prompts": False,
                "log_response": False,
            },
            "display": {"use_progress_bar": False},
            "prompts": "config/prompts.json",
        },
    }


@pytest.fixture
def tiny_csv_bytes(fixtures_dir: Path) -> bytes:
    """Return the raw bytes of ``tiny.csv`` for upload tests.

    Args:
        fixtures_dir (Path): Fixtures directory.

    Returns:
        bytes: Raw CSV payload.
    """
    return (fixtures_dir / "tiny.csv").read_bytes()


@pytest.fixture
def summary_csv_fixture_path(
    server_paths,
    fixtures_dir: Path,
) -> Path:
    """Copy ``summary.csv`` into a run directory and return the absolute path.

    :class:`server.services.results_preview.ResultsPreviewService`
    expects each artifact under ``<runs_dir>/<run_id>/summary.csv``;
    this fixture sets up the most common shape so tests can ask for a
    preview of a known file.

    Args:
        server_paths: Isolated :class:`ServerPaths`.
        fixtures_dir (Path): Fixtures directory.

    Returns:
        Path: Absolute path of the copied artifact.
    """
    run_dir = server_paths.runs_dir / "preview_fixture_run"
    run_dir.mkdir(parents=True, exist_ok=True)
    summary_bytes = (fixtures_dir / "summary.csv").read_bytes()
    destination = run_dir / "summary.csv"
    destination.write_bytes(summary_bytes)
    return destination


@pytest.fixture
def openrouter_models_json(fixtures_dir: Path) -> Dict[str, Any]:
    """Return the parsed ``openrouter_models.json`` fixture.

    Args:
        fixtures_dir (Path): Fixtures directory.

    Returns:
        Dict[str, Any]: Representative OpenRouter ``/api/v1/models``
        response body.
    """
    import json

    with (fixtures_dir / "openrouter_models.json").open("r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


@pytest.fixture
def openai_models_json(fixtures_dir: Path) -> Dict[str, Any]:
    """Return the parsed ``openai_models.json`` fixture.

    Args:
        fixtures_dir (Path): Fixtures directory.

    Returns:
        Dict[str, Any]: Representative OpenAI ``/v1/models`` response
        body.
    """
    import json

    with (fixtures_dir / "openai_models.json").open("r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


@pytest.fixture(autouse=True)
def _quiet_get_settings_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear the :func:`server.settings.get_settings` cache around each test.

    Without this, a test that mutates env vars after
    ``get_settings()`` has been called elsewhere in the session would
    see the *first* call's cached settings. The autouse fixture runs
    before every test and clears the cache unconditionally.
    """
    from server.settings import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


__all__: List[str] = [
    "eager_celery_app",
    "fake_redis_client",
    "fixtures_dir",
    "flow_validator",
    "isolated_data_dir",
    "isolated_server_settings",
    "openai_models_json",
    "openrouter_models_json",
    "patch_build_redis_client",
    "project_root",
    "recorded_celery_app",
    "server_paths",
    "summary_csv_fixture_path",
    "test_client",
    "tiny_csv_bytes",
    "valid_flow_body",
]
