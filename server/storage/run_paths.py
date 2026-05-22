"""Per-run directory layout under :attr:`ServerPaths.runs_dir`.

Every run created by :class:`server.services.run_dispatcher.RunDispatcher`
owns one directory keyed by ``run_id`` under
``<data_dir>/runs/<run_id>/``. This module is the single source of
truth for the filenames inside that directory: the written flow YAML,
the output CSVs, the worker log file, and the checkpoint directory used
by :class:`src.flow_builder._Checkpoint`.

Contents and relationships
--------------------------

- :class:`RunPaths` — frozen dataclass holding every file and
  subdirectory path for one ``run_id``. Exposes both absolute
  :class:`pathlib.Path` attributes (for services that read or create
  files directly) and project-root-relative POSIX string attributes
  (for values that must land in the flow YAML and be resolved by a
  different process with a different OS).
- :meth:`RunPaths.for_run_id` — factory that derives every path from a
  :class:`server.storage.paths.ServerPaths` and a ``run_id`` string.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.services.run_dispatcher` calls :meth:`RunPaths.for_run_id`
  when enqueuing a new run, rewrites the flow YAML's ``output.*`` and
  ``logging.file`` entries to the project-root-relative POSIX strings
  exposed here, and writes the resulting YAML at
  :attr:`RunPaths.flow_yaml_path`.
- :mod:`server.services.run_registry` reads
  :attr:`RunPaths.completed_entities_path` when populating
  :attr:`server.schemas.run.RunStatusDTO.completed_entity_count`.
- :mod:`server.workers.flow_task` reads :attr:`RunPaths.flow_yaml_path`
  and passes it to :func:`src.flow_builder.build_flow`.

Invariants enforced by this module
----------------------------------

- The checkpoint directory path returned here
  (:attr:`RunPaths.checkpoint_dir`) is exactly what
  :class:`src.flow_builder._Checkpoint` writes to, given that the flow
  YAML's ``output.summary_csv`` lives under
  :attr:`RunPaths.output_dir`. If either piece changes, both must be
  updated together.
- Every absolute ``Path`` attribute is absolute; every
  ``*_relative_posix`` attribute is project-root-relative (no leading
  slash, no drive letter, forward slashes only).
- The relative-POSIX forms always resolve to the corresponding
  absolute paths when interpreted against the project root (i.e.
  ``/app`` in the container, ``<cwd>`` on the host if the host CWD is
  the project root).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from server.storage.paths import ServerPaths


@dataclass(frozen=True)
class RunPaths:
    """On-disk layout for one run, keyed by ``run_id``.

    Attributes:
        run_id (str): Opaque run identifier (UUID-style string).
        run_dir (Path): ``<runs_dir>/<run_id>``; root of this run's
            artefacts.
        flow_yaml_path (Path): ``<run_dir>/flow.yml``; the flow YAML
            written by :class:`server.services.run_dispatcher.RunDispatcher`
            with ``output.*`` rewritten so the runner writes into this
            run's directory.
        output_dir (Path): ``<run_dir>``; parent of the CSVs written by
            :class:`src.flow_builder.FlowRunner`. Intentionally the same
            as :attr:`run_dir` so the checkpoint directory created by
            :class:`src.flow_builder._Checkpoint` sits under the run
            root.
        checkpoint_dir (Path): ``<run_dir>/.checkpoint``; directory used
            by :class:`src.flow_builder._Checkpoint` for
            ``completed_entities.json``.
        completed_entities_path (Path):
            ``<checkpoint_dir>/completed_entities.json``; read by
            :class:`server.services.run_registry.RunRegistry` to
            surface :attr:`server.schemas.run.RunStatusDTO.completed_entity_count`.
        worker_log_path (Path): ``<run_dir>/worker.log``; target for the
            flow's ``flow.logging.file`` rewrite.
        run_dir_relative_posix (str): ``run_dir`` expressed as a
            project-root-relative POSIX string (for example
            ``server/data/runs/<run_id>``). The run dispatcher embeds
            this in the rewritten flow YAML so the worker (Linux
            container) and the web (potentially Windows host) agree on
            the same output location regardless of OS.
        worker_log_path_relative_posix (str): ``worker_log_path`` in the
            same project-root-relative POSIX form.

    Methods:
        for_run_id: Build a :class:`RunPaths` for ``run_id`` relative to
            a :class:`ServerPaths`.
        ensure_run_dir_exists: Create :attr:`run_dir` on disk if it is
            not already present.
    """

    run_id: str
    run_dir: Path
    flow_yaml_path: Path
    output_dir: Path
    checkpoint_dir: Path
    completed_entities_path: Path
    worker_log_path: Path
    run_dir_relative_posix: str
    worker_log_path_relative_posix: str

    @classmethod
    def for_run_id(cls, paths: ServerPaths, run_id: str) -> "RunPaths":
        """Derive every per-run path from ``paths`` and ``run_id``.

        Does not create the directory; the caller decides whether the
        run is new (create) or being resumed (reuse existing).

        Args:
            paths (ServerPaths): The top-level on-disk layout.
            run_id (str): The run identifier to pin this directory to.

        Returns:
            RunPaths: A frozen dataclass with every path populated.
        """
        run_dir = (paths.runs_dir / run_id).resolve()
        checkpoint_dir = run_dir / ".checkpoint"
        run_dir_relative_posix = f"{paths.runs_dir_relative_posix}/{run_id}"
        return cls(
            run_id=run_id,
            run_dir=run_dir,
            flow_yaml_path=run_dir / "flow.yml",
            output_dir=run_dir,
            checkpoint_dir=checkpoint_dir,
            completed_entities_path=checkpoint_dir / "completed_entities.json",
            worker_log_path=run_dir / "worker.log",
            run_dir_relative_posix=run_dir_relative_posix,
            worker_log_path_relative_posix=f"{run_dir_relative_posix}/worker.log",
        )

    def ensure_run_dir_exists(self) -> None:
        """Create :attr:`run_dir` on disk if it is not already present.

        Idempotent. Called by
        :class:`server.services.run_dispatcher.RunDispatcher` before
        writing the flow YAML.

        Returns:
            None.
        """
        self.run_dir.mkdir(parents=True, exist_ok=True)
