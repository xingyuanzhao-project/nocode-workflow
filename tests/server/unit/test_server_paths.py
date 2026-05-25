"""Unit tests for :mod:`server.storage.paths` and :mod:`server.storage.run_paths`.

The paths module is the single source of truth for how
``server/data/<subdir>`` maps to the project-root-relative POSIX
string written into flow YAMLs. Every OS-crossing bug we have ever
had lived here, so the tests pin every invariant.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from server.settings import ServerSettings
from server.storage.paths import ServerPaths, _project_root_relative_posix
from server.storage.run_paths import RunPaths


class TestProjectRootRelativePosix:
    def test_rejects_path_outside_project_root(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside"
        outside.mkdir()
        with pytest.raises(ValueError, match="is not inside project root"):
            _project_root_relative_posix(outside)

    def test_returns_forward_slashes(self, project_root: Path) -> None:
        inside = project_root / "server" / "data"
        assert _project_root_relative_posix(inside) == "server/data"


class TestServerPathsFromSettings:
    def test_all_directories_exist_after_build(self, server_paths: ServerPaths) -> None:
        assert server_paths.workflows_dir.is_dir()
        assert server_paths.codebooks_dir.is_dir()
        assert server_paths.data_dir.is_dir()
        assert server_paths.runs_dir.is_dir()

    def test_relative_posix_fields_are_forward_slash(self, server_paths: ServerPaths) -> None:
        assert "\\" not in server_paths.data_dir_relative_posix
        assert "\\" not in server_paths.runs_dir_relative_posix
        assert server_paths.data_dir_relative_posix.endswith("/data")
        assert server_paths.runs_dir_relative_posix.endswith("/runs")

    def test_from_settings_rejects_data_dir_outside_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        outside = tmp_path / "outside_project"
        outside.mkdir()
        monkeypatch.setenv("ACADEMIC_PIPELINE_SERVER_ROOT", str(outside))
        settings = ServerSettings()
        with pytest.raises(ValueError, match="is not inside project root"):
            ServerPaths.from_settings(settings)


class TestRunPaths:
    def test_run_paths_derive_from_run_id(self, server_paths: ServerPaths) -> None:
        run_paths = RunPaths.for_run_id(server_paths, "abc123")
        assert run_paths.run_id == "abc123"
        assert run_paths.run_dir.name == "abc123"
        assert run_paths.flow_yaml_path.name == "flow.yml"
        assert run_paths.completed_entities_path.parent.name == ".checkpoint"

    def test_run_paths_relative_posix_matches_run_dir(self, server_paths: ServerPaths) -> None:
        run_paths = RunPaths.for_run_id(server_paths, "xyz")
        assert run_paths.run_dir_relative_posix.endswith("/runs/xyz")
        assert run_paths.worker_log_path_relative_posix.endswith("/runs/xyz/worker.log")

    def test_ensure_run_dir_exists_is_idempotent(self, server_paths: ServerPaths) -> None:
        run_paths = RunPaths.for_run_id(server_paths, "make_me")
        run_paths.ensure_run_dir_exists()
        run_paths.ensure_run_dir_exists()  # Second call must not raise.
        assert run_paths.run_dir.is_dir()
