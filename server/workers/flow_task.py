"""Celery task that executes one flow run, keyed by ``run_id``.

The task body is intentionally narrow: resolve the run's paths, call
:func:`src.flow_builder.build_flow` with ``resume=True``, and run the
resulting :class:`src.flow_builder.FlowRunner`. Status tracking lives
in :mod:`server.workers.signals` so the task body does not mix
"execute the flow" with "update the user-visible status".

Contents and relationships
--------------------------

- :func:`execute_flow` — the single ``@celery_app.task`` in this
  scaffold.
- :func:`_resolve_taxonomy_override` — walks ``flow.nodes[]`` for a
  ``codebook`` node, reads its ``config.codebook_id``, and loads the
  taxonomy body from
  :class:`server.services.taxonomy_repository.TaxonomyRepository`.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.celery_app` autodiscovers this task under the name
  ``server.workers.flow_task.execute_flow``.
- :class:`server.services.run_dispatcher.RunDispatcher` enqueues the
  task by name via
  :data:`server.services.run_dispatcher.FLOW_TASK_NAME`.

Invariants enforced by this module
----------------------------------

- The task body **always** passes ``resume=True`` to
  :func:`src.flow_builder.build_flow`. Rationale:

  - On a fresh run the checkpoint directory is empty, so
    ``resume=True`` is a no-op.
  - On a retry (after an ``acks_late`` requeue) or an explicit
    ``POST /api/flow/resume/{run_id}`` the checkpoint file lists the
    entities that already completed, so the flow skips them.

  Making this conditional would introduce two code paths for what is
  a single idempotent behaviour; the checkpoint itself is the truth.
- The task does **not** declare ``autoretry_for``. Transient LLM
  errors are retried inside
  :class:`src.processors.AsyncMessyTextProcessor` via
  ``AsyncOpenAI(max_retries=…)`` and worker-death requeues are handled
  by ``task_acks_late``. Stacking a Celery-level retry on top would
  cause double retries. Hard failures surface as
  :attr:`server.schemas.run.RunStatus.FAILED`; the user clicks
  "resume" to re-enqueue with the same ``run_id`` and the same
  checkpoint.
- The task opens its own asyncio event loop via :func:`asyncio.run`.
  This is compatible with the ``--pool=solo`` worker configuration
  and would conflict with ``prefork`` or ``gevent``; the worker pool
  choice is pinned in :mod:`server.celery_app`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from src.flow_builder import build_flow

from server.celery_app import celery_app
from server.settings import get_settings
from server.storage.paths import ServerPaths
from server.storage.run_paths import RunPaths
from server.services.taxonomy_repository import TaxonomyRepository


def _resolve_taxonomy_override(
    flow_yaml_path: Path, paths: ServerPaths
) -> Optional[Dict[str, Any]]:
    """Load taxonomy data from the repository when the flow uses a URI.

    Walks ``flow.nodes[]`` looking for the single ``codebook`` node.
    When that node's ``config.codebook_id`` is set, the taxonomy body
    for that id is loaded from the :class:`TaxonomyRepository`. When
    only ``config.codebook_path`` is set, the file is loaded from disk
    by :func:`build_flow` itself, so this function returns ``None``.

    Args:
        flow_yaml_path (Path): Path to the run's ``flow.yml``.
        paths (ServerPaths): Server layout, needed to construct a
            :class:`TaxonomyRepository`.

    Returns:
        Optional[Dict[str, Any]]: The taxonomy body if a codebook id is
        declared, otherwise ``None``.

    Raises:
        FileNotFoundError: If the taxonomy id does not exist in the
            repository.
    """
    with flow_yaml_path.open("r", encoding="utf-8") as yaml_file:
        raw_document = yaml.safe_load(yaml_file) or {}
    flow_block = raw_document.get("flow") or {}
    nodes_list = flow_block.get("nodes") or []
    if not isinstance(nodes_list, list):
        return None
    codebook_id: Optional[str] = None
    for node in nodes_list:
        if not isinstance(node, dict) or node.get("type") != "codebook":
            continue
        node_config = node.get("config") or {}
        if not isinstance(node_config, dict):
            continue
        candidate_id = node_config.get("codebook_id")
        if isinstance(candidate_id, str) and candidate_id:
            codebook_id = candidate_id
            break
    if codebook_id is None:
        return None
    repository = TaxonomyRepository(paths=paths)
    taxonomy_response = repository.get(codebook_id)
    return taxonomy_response.taxonomy


@celery_app.task(
    bind=True,
    name="server.workers.flow_task.execute_flow",
    acks_late=True,
    reject_on_worker_lost=True,
)
def execute_flow(self, run_id: str) -> None:  # noqa: ARG001  (bind=True injects self)
    """Execute the flow stored at ``<run_dir>/flow.yml`` for ``run_id``.

    When the flow YAML's ``taxonomy`` field is a ``taxonomy://<id>``
    URI, the taxonomy body is resolved from the server's
    :class:`TaxonomyRepository` and passed as ``taxonomy_override`` to
    :func:`build_flow`. Otherwise the builder loads the taxonomy from
    the filesystem path as before.

    Args:
        run_id (str): Identifier of the run to execute. Pins the
            directory ``<runs_dir>/<run_id>/`` and the YAML at
            ``<runs_dir>/<run_id>/flow.yml``.

    Returns:
        None.

    Raises:
        FileNotFoundError: If the flow YAML does not exist at the
            pinned path, or if the taxonomy URI references a
            non-existent taxonomy in the repository.
        Exception: Propagates any exception raised by
            :meth:`src.flow_builder.FlowRunner.run_async`. Celery's
            ``task_failure`` signal (handled by
            :mod:`server.workers.signals`) records the failure on the
            :class:`server.services.run_registry.RunRegistry`.
    """
    paths = ServerPaths.from_settings(get_settings())
    run_paths = RunPaths.for_run_id(paths, run_id)
    taxonomy_override = _resolve_taxonomy_override(
        run_paths.flow_yaml_path, paths
    )
    flow_runner = build_flow(
        run_paths.flow_yaml_path,
        resume=True,
        taxonomy_override=taxonomy_override,
    )
    asyncio.run(flow_runner.run_async())
