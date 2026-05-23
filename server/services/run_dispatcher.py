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
- The output rewrite in :func:`_rewrite_output_paths` covers every
  field on :class:`src.flow_loader.OutputConfig` plus
  :attr:`src.flow_loader.LoggingConfig.file`, so nothing from the
  original flow YAML writes outside the run directory.
- :meth:`submit` validates the flow before enqueuing; invalid flows
  raise :class:`ValueError` and never create a run directory.
"""

from __future__ import annotations

import copy
import uuid
from typing import Any, Dict

import yaml
from celery import Celery

from server.schemas.run import RunStartResponse, RunStatus
from server.services.flow_validation import FlowValidator
from server.services.run_registry import RunRegistry
from server.storage.paths import ServerPaths
from server.storage.run_paths import RunPaths


FLOW_TASK_NAME: str = "server.workers.flow_task.execute_flow"
"""Name under which :func:`server.workers.flow_task.execute_flow` is
registered with Celery. Referenced by :meth:`RunDispatcher.submit` so
the dispatcher stays decoupled from the workers module."""


_OUTPUT_NODE_TYPES = frozenset({"csv_output", "json_output"})


def _rewrite_output_paths(
    flow_definition: Dict[str, Any], run_paths: RunPaths
) -> Dict[str, Any]:
    """Return a copy of ``flow_definition`` with every output path pinned to ``run_paths``.

    The flow body is the new graph format. The dispatcher walks
    ``nodes[]`` to find the single output node (``csv_output`` /
    ``json_output``) and rewrites its ``config.output_path`` plus every
    entry of ``config.artifact_paths`` so they sit under the run
    directory. It also rewrites
    ``settings.logging.file`` to :attr:`RunPaths.worker_log_path_relative_posix`.

    Per-run filenames:

    - ``output_path`` → ``<run_dir_relative_posix>/summary.csv``
    - ``artifact_paths[0]`` → ``<run_dir>/results.csv`` (if present)
    - ``artifact_paths[1]`` → ``<run_dir>/states.csv`` (if present)
    - ``artifact_paths[2]`` → ``<run_dir>/spans.csv`` (if present)
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

    artifact_filenames = ["results.csv", "states.csv", "spans.csv"]
    nodes_list = rewritten.get("nodes")
    if isinstance(nodes_list, list):
        for node in nodes_list:
            if not isinstance(node, dict):
                continue
            if node.get("type") not in _OUTPUT_NODE_TYPES:
                continue
            node_config = node.setdefault("config", {})
            if not isinstance(node_config, dict):
                node_config = {}
                node["config"] = node_config
            node_config["output_path"] = f"{run_dir}/summary.csv"
            artifact_paths = node_config.get("artifact_paths")
            if isinstance(artifact_paths, list):
                rewritten_artifacts = list(artifact_paths)
                for index in range(min(len(rewritten_artifacts), 3)):
                    if rewritten_artifacts[index] is None:
                        continue
                    rewritten_artifacts[index] = (
                        f"{run_dir}/{artifact_filenames[index]}"
                    )
                node_config["artifact_paths"] = rewritten_artifacts

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
        registers the run as ``queued``, and enqueues the Celery task.

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

        self.registry.create(run_id)
        self.celery_app.send_task(FLOW_TASK_NAME, args=[run_id])
        return RunStartResponse(run_id=run_id, status=RunStatus.QUEUED)

    def resume(self, run_id: str) -> RunStartResponse:
        """Re-enqueue an existing run.

        Does not rewrite the flow YAML — the file at
        :attr:`RunPaths.flow_yaml_path` is already correct from the
        original :meth:`submit`. The Celery task body always passes
        ``resume=True`` to :func:`src.flow_builder.build_flow`, so the
        checkpoint skips already-completed entities.

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
        self.registry.create(run_id)
        self.celery_app.send_task(FLOW_TASK_NAME, args=[run_id])
        return RunStartResponse(run_id=run_id, status=RunStatus.QUEUED)
