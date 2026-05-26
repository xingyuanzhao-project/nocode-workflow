"""Service that writes per-run flow YAMLs and enqueues the Celery task.

The dispatcher is the *only* place that mints new ``run_id`` values,
the *only* place that rewrites the flow YAML's ``output.*`` paths so
they land under the run directory, and the *only* place that calls
:meth:`celery.Celery.send_task`. Keeping all three responsibilities
here means the worker task body can stay narrow (load YAML, run the
flow) and the HTTP routes stay thin (call a single dispatcher method).

Contents and relationships
--------------------------

- :class:`RunDispatcher` — service with :meth:`submit` and
  :meth:`resume` methods.
- :data:`FLOW_TASK_NAME` — Celery task name used by :meth:`send_task`.
  Pinned as a module constant so the dispatcher does not import from
  :mod:`server.workers`, preserving the one-way dependency from
  ``workers`` to ``services``.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.routes.flow` calls :meth:`RunDispatcher.submit` from
  ``POST /api/flow/run`` and ``POST /api/flow/{id}/run``, and calls
  :meth:`RunDispatcher.resume` from ``POST /api/flow/resume/{run_id}``.

Invariants enforced by this module
----------------------------------

- A ``run_id`` pins exactly one output directory; the flow YAML on
  disk at :attr:`server.storage.run_paths.RunPaths.flow_yaml_path` is
  immutable after :meth:`submit` returns.
- The output rewrite in :func:`_rewrite_output_paths` covers
  ``output_path`` and :attr:`src.flow_loader.LoggingConfig.file`, so
  nothing from the original flow YAML writes outside the run directory.
- :meth:`submit` validates the flow before enqueuing; invalid flows
  raise :class:`ValueError` and never create a run directory.
"""

from __future__ import annotations

import copy
import json as _json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from celery import Celery

from server.schemas.run import RunStartResponse, RunStatus
from server.services.flow_validation import FlowValidator
from server.services.run_registry import RunRegistry
from server.storage.paths import ServerPaths
from server.storage.run_paths import RunPaths

_log = logging.getLogger(__name__)

FLOW_TASK_NAME: str = "server.workers.flow_task.execute_flow"
"""Name under which :func:`server.workers.flow_task.execute_flow` is
registered with Celery. Referenced by :meth:`RunDispatcher.submit` so
the dispatcher stays decoupled from the workers module."""


_OUTPUT_NODE_TYPES = frozenset({"csv_output", "json_output"})
_INPUT_NODE_TYPES = frozenset({"csv_input", "json_input"})


def _count_input_rows(flow_definition: Dict[str, Any]) -> int:
    """Best-effort count of rows the flow will process.

    Walks the node list for a data-source node, reads the referenced
    file, and counts rows.  Respects ``settings.processing_limit``
    when present.  Returns ``0`` on any failure so that progress bars
    degrade gracefully to an indeterminate display.
    """
    nodes = flow_definition.get("nodes")
    if not isinstance(nodes, list):
        return 0

    file_path: Optional[Path] = None
    node_type: Optional[str] = None
    for node in nodes:
        if not isinstance(node, dict):
            continue
        ntype = node.get("type")
        if ntype not in _INPUT_NODE_TYPES:
            continue
        config = node.get("config")
        if not isinstance(config, dict):
            continue
        selected = config.get("selected_file")
        if isinstance(selected, str) and selected:
            candidate = Path(selected)
            if candidate.is_file():
                file_path = candidate
                node_type = ntype
                break

    if file_path is None:
        return 0

    try:
        if node_type == "csv_input":
            with file_path.open("r", encoding="utf-8", errors="replace") as fh:
                row_count = max(sum(1 for _ in fh) - 1, 0)
        else:
            raw = file_path.read_text(encoding="utf-8", errors="replace").strip()
            if raw.startswith("["):
                row_count = len(_json.loads(raw))
            else:
                row_count = sum(1 for line in raw.splitlines() if line.strip())
    except (OSError, _json.JSONDecodeError, UnicodeDecodeError):
        return 0

    settings = flow_definition.get("settings")
    if isinstance(settings, dict):
        limit = settings.get("processing_limit")
        if isinstance(limit, int) and limit > 0:
            row_count = min(row_count, limit)

    return row_count


def _rewrite_output_paths(
    flow_definition: Dict[str, Any], run_paths: RunPaths
) -> Dict[str, Any]:
    """Return a copy of ``flow_definition`` with every output path pinned to ``run_paths``.

    The flow body is the new graph format. The dispatcher walks
    ``nodes[]`` to find the single output node (``csv_output`` /
    ``json_output``) and rewrites its ``config.output_path`` so it sits
    under the run directory. It also rewrites
    ``settings.logging.file`` to :attr:`RunPaths.worker_log_path_relative_posix`.

    Per-run filenames:

    - ``output_path`` → ``<run_dir_relative_posix>/summary.csv``
    - ``settings.logging.file`` →
      :attr:`RunPaths.worker_log_path_relative_posix`

    All rewritten values are project-root-relative POSIX strings so that
    the YAML on disk resolves identically in the FastAPI web process and
    in the Celery worker container, which may run on different
    operating systems during development but always share the project
    root as their working directory.

    The rewrite is a deep copy; the input dict is never mutated.

    Args:
        flow_definition (Dict[str, Any]): Raw flow body in the new graph
            format (``nodes[]`` / ``edges[]`` / ``settings``).
        run_paths (RunPaths): The run's on-disk layout.

    Returns:
        Dict[str, Any]: Deep copy with paths rewritten.
    """
    rewritten = copy.deepcopy(flow_definition)
    run_dir = run_paths.run_dir_relative_posix

    nodes_list = rewritten.get("nodes")
    if isinstance(nodes_list, list):
        output_index = 0
        for node in nodes_list:
            if not isinstance(node, dict):
                continue
            if node.get("type") not in _OUTPUT_NODE_TYPES:
                continue
            node_config = node.setdefault("config", {})
            if not isinstance(node_config, dict):
                node_config = {}
                node["config"] = node_config
            ext = "json" if node.get("type") == "json_output" else "csv"
            suffix = f"_{output_index}" if output_index > 0 else ""
            node_config["output_path"] = f"{run_dir}/summary{suffix}.{ext}"
            output_index += 1

    settings_block = rewritten.setdefault("settings", {})
    if not isinstance(settings_block, dict):
        settings_block = {}
        rewritten["settings"] = settings_block
    logging_block = settings_block.setdefault("logging", {})
    if not isinstance(logging_block, dict):
        logging_block = {}
        settings_block["logging"] = logging_block
    logging_block["file"] = run_paths.worker_log_path_relative_posix

    return rewritten


class RunDispatcher:
    """Service that creates run directories and enqueues Celery tasks.

    Attributes:
        paths (ServerPaths): On-disk layout.
        registry (RunRegistry): Status store written on enqueue.
        celery_app (Celery): Celery instance used to call
            :meth:`Celery.send_task`.
        validator (FlowValidator): Validates flows before enqueue.

    Methods:
        submit: Validate a flow, write its YAML to a new run directory,
            and enqueue the task.
        resume: Re-enqueue an existing run without touching its YAML.
    """

    def __init__(
        self,
        paths: ServerPaths,
        registry: RunRegistry,
        celery_app: Celery,
        validator: FlowValidator,
    ) -> None:
        """Store the injected collaborators.

        Args:
            paths (ServerPaths): On-disk layout.
            registry (RunRegistry): Status store written on enqueue.
            celery_app (Celery): Celery instance used to call
                :meth:`Celery.send_task`.
            validator (FlowValidator): Validates flows before enqueue.
        """
        self.paths = paths
        self.registry = registry
        self.celery_app = celery_app
        self.validator = validator

    def submit(self, flow_definition: Dict[str, Any]) -> RunStartResponse:
        """Enqueue a fresh run of ``flow_definition``.

        Validates the flow, mints a new ``run_id``, creates the run
        directory, writes the flow YAML with rewritten output paths,
        and enqueues a Celery task.

        Args:
            flow_definition (Dict[str, Any]): Raw flow body.

        Returns:
            RunStartResponse: The new ``run_id`` and its initial status.

        Raises:
            ValueError: If the flow fails validation.
        """
        validation_response = self.validator.validate(flow_definition)
        if not validation_response.valid:
            raise ValueError(validation_response.model_dump_json())

        run_id = uuid.uuid4().hex
        run_paths = RunPaths.for_run_id(self.paths, run_id)
        run_paths.ensure_run_dir_exists()

        rewritten_flow = _rewrite_output_paths(flow_definition, run_paths)
        document = {"flow": rewritten_flow}
        with run_paths.flow_yaml_path.open("w", encoding="utf-8") as file_handle:
            yaml.safe_dump(document, file_handle, sort_keys=False)

        total_rows = _count_input_rows(flow_definition)
        self.registry.create(run_id, total_row_count=total_rows)
        self.celery_app.send_task(FLOW_TASK_NAME, args=[run_id])
        return RunStartResponse(run_id=run_id, status=RunStatus.QUEUED)

    def resume(self, run_id: str) -> RunStartResponse:
        """Re-enqueue an existing run.

        Does not rewrite the flow YAML — the file at
        :attr:`RunPaths.flow_yaml_path` is already correct from the
        original :meth:`submit`.

        Args:
            run_id (str): Identifier of an existing run.

        Returns:
            RunStartResponse: ``run_id`` echoed back with status
            ``queued``.

        Raises:
            FileNotFoundError: If no flow YAML exists at
                :attr:`RunPaths.flow_yaml_path`.
        """
        run_paths = RunPaths.for_run_id(self.paths, run_id)
        if not run_paths.flow_yaml_path.exists():
            raise FileNotFoundError(
                f"Run {run_id!r} has no flow YAML at {run_paths.flow_yaml_path}; "
                "cannot resume."
            )
        total_rows = 0
        try:
            with run_paths.flow_yaml_path.open("r", encoding="utf-8") as fh:
                doc = yaml.safe_load(fh)
            if isinstance(doc, dict):
                flow_def = doc.get("flow", {})
                if isinstance(flow_def, dict):
                    total_rows = _count_input_rows(flow_def)
        except (OSError, yaml.YAMLError):
            pass
        self.registry.create(run_id, total_row_count=total_rows)
        self.celery_app.send_task(FLOW_TASK_NAME, args=[run_id])
        return RunStartResponse(run_id=run_id, status=RunStatus.QUEUED)
