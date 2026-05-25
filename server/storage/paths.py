"""Top-level on-disk layout for server runtime directories.

Centralises the directory hierarchy used by every service so nothing
else has to know ``server/workflows/`` lives next to
``server/codebooks/`` lives next to ``server/data/`` lives next to
``server/runs/``. Swapping the root directory is a one-setting change.

Contents and relationships
--------------------------

- :class:`ServerPaths` — frozen dataclass holding the runtime
  directories. Created once per process via
  :meth:`ServerPaths.from_settings`, which also calls ``mkdir`` so every
  directory exists before the first service reads or writes. The class
  additionally exposes project-root-relative POSIX string forms of the
  directories (``data_dir_relative_posix`` etc.), used when a path
  must appear in a flow YAML or response DTO that crosses process and
  OS boundaries (for example Windows host to Linux worker container).

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.services.flow_repository` reads
  :attr:`ServerPaths.workflows_dir`.
- :mod:`server.services.taxonomy_repository` reads
  :attr:`ServerPaths.codebooks_dir`.
- :mod:`server.services.csv_uploader` reads
  :attr:`ServerPaths.data_dir` for the absolute write target and
  :attr:`ServerPaths.data_dir_relative_posix` for the
  ``stored_path`` it returns to clients.
- :mod:`server.services.run_dispatcher`,
  :mod:`server.services.run_registry`, and
  :mod:`server.workers.flow_task` all derive per-run paths from
  :attr:`ServerPaths.runs_dir` via
  :class:`server.storage.run_paths.RunPaths`.

Invariants enforced by this module
----------------------------------

- All directories must lie inside the project root
  (``<project_root>/...``). The relative-POSIX helpers are computed
  from that invariant; :meth:`ServerPaths.from_settings` raises
  :class:`ValueError` if it is violated.
- :meth:`ServerPaths.from_settings` is idempotent; calling it twice
  returns two equivalent dataclass instances and does not recreate
  existing directories.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from server.settings import ServerSettings

_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
"""Absolute path of the project root.

Derived from this file's location (``server/storage/paths.py``). Used
to express :class:`ServerPaths` directories as project-root-relative
POSIX strings that the FastAPI web process and the Celery worker agree
on, even if they run on different operating systems.
"""


def _project_root_relative_posix(target: Path) -> str:
    """Return ``target`` written as a project-root-relative POSIX string.

    Args:
        target (Path): An absolute path that must lie inside
            :data:`_PROJECT_ROOT`.

    Returns:
        str: ``target`` with forward slashes, no leading ``/``, no
        Windows drive letter. For example
        ``server/data/uploads``.

    Raises:
        ValueError: If ``target`` is not inside :data:`_PROJECT_ROOT`.
    """
    try:
        return target.relative_to(_PROJECT_ROOT).as_posix()
    except ValueError as exc:
        raise ValueError(
            f"{target} is not inside project root {_PROJECT_ROOT}; "
            "set ACADEMIC_PIPELINE_SERVER_ROOT to a path under the project root so "
            "host (Windows) and worker (container Linux) resolve the same "
            "relative paths in flow YAMLs."
        ) from exc


@dataclass(frozen=True)
class ServerPaths:
    """Top-level on-disk directory layout for the server package.

    Attributes:
        workflows_dir (Path): ``<server_root>/workflows``; saved flow
            YAMLs (user-created and seeded).
        codebooks_dir (Path): ``<server_root>/codebooks``; saved
            codebook JSONs.
        data_dir (Path): ``<server_root>/data``; user-uploaded CSVs.
        runs_dir (Path): ``<server_root>/runs``; per-run artefact
            directories, each keyed by ``run_id``.
        data_dir_relative_posix (str): ``data_dir`` expressed relative
            to the project root with forward slashes (for example
            ``server/data``). Used anywhere a path must travel between
            the web process and the worker as a string (flow YAMLs,
            upload response DTOs).
        runs_dir_relative_posix (str): ``runs_dir`` in the same
            project-root-relative POSIX form.

    Methods:
        from_settings: Construct a :class:`ServerPaths` from a
            :class:`ServerSettings` and ensure every directory exists.
    """

    workflows_dir: Path
    codebooks_dir: Path
    data_dir: Path
    runs_dir: Path
    data_dir_relative_posix: str
    runs_dir_relative_posix: str

    @classmethod
    def from_settings(cls, settings: ServerSettings) -> "ServerPaths":
        """Build a :class:`ServerPaths` and create every directory on disk.

        Args:
            settings (ServerSettings): The process settings; only
                :attr:`ServerSettings.server_root` is read.

        Returns:
            ServerPaths: A frozen dataclass whose directories all
            exist on disk and whose relative-POSIX fields are computed
            against the project root.

        Raises:
            ValueError: If a directory resolves outside the
                project root. See :func:`_project_root_relative_posix`.
        """
        server_root = Path(settings.server_root).resolve()
        workflows_dir = server_root / "workflows"
        codebooks_dir = server_root / "codebooks"
        data_dir = server_root / "data"
        runs_dir = server_root / "runs"
        for directory in (workflows_dir, codebooks_dir, data_dir, runs_dir):
            directory.mkdir(parents=True, exist_ok=True)
        data_dir_relative_posix = _project_root_relative_posix(data_dir)
        runs_dir_relative_posix = _project_root_relative_posix(runs_dir)
        return cls(
            workflows_dir=workflows_dir,
            codebooks_dir=codebooks_dir,
            data_dir=data_dir,
            runs_dir=runs_dir,
            data_dir_relative_posix=data_dir_relative_posix,
            runs_dir_relative_posix=runs_dir_relative_posix,
        )
