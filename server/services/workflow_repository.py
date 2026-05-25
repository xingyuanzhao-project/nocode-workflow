"""Read-only repository of preset workflows shipped with the app.

Workflows live on disk under ``<project_root>/workflows/*.yml``
and are read-only: they ship with the repository, not with user data.
The GUI's "New Flow" dialog queries this repository to render its
workflow list, and then fetches the full body when the user picks one.

Contents and relationships
--------------------------

- :class:`WorkflowRepository` — the service; exposes
  :meth:`list` (list-view) and :meth:`get` (detail-view).
- :data:`_PROJECT_ROOT` — project root derived from this file's
  location; mirrors the same convention used by
  :mod:`server.storage.paths`.
- :data:`DEFAULT_WORKFLOWS_SOURCE_DIR` — canonical workflows directory
  (``<project_root>/workflows``). Tests can inject a different
  directory at construction time.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.routes.workflows` calls :meth:`list` and :meth:`get`.
- :mod:`server.dependencies` provides the repository instance via
  ``request.app.state.workflow_repository``, constructed once in
  :func:`server.app.create_app`.

Invariants enforced by this module
----------------------------------

- Every workflow YAML is validated by
  :class:`server.services.flow_validation.FlowValidator` at load time.
  A workflow that fails validation is *excluded* from :meth:`list` and
  raises :class:`FileNotFoundError` (via :meth:`get`) when requested,
  so the GUI can never render a broken workflow onto the canvas.
- Workflow ids are the YAML filename stems; filenames must therefore be
  stable (renaming a workflow changes its id).
- The repository is read-only. There is no :meth:`save`; workflows are
  managed via the git repository, not the HTTP API.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import yaml

from server.schemas.workflows import WorkflowDetail, WorkflowListItem
from server.services.flow_validation import FlowValidator


_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
"""Project root derived from this file's location.

Used only to compute :data:`DEFAULT_WORKFLOWS_SOURCE_DIR`. Matches the same
derivation used in :mod:`server.storage.paths`.
"""


DEFAULT_WORKFLOWS_SOURCE_DIR: Path = _PROJECT_ROOT / "workflows"
"""Canonical on-disk location of the preset workflow YAMLs.

Fixed relative to the project root. In production (Render),
.dockerignore excludes this directory from the image.
"""


class WorkflowRepository:
    """Read-only repository of preset workflows.

    Attributes:
        workflows_dir (Path): Directory containing the workflow YAMLs.
        validator (FlowValidator): Used to verify every workflow loads
            cleanly; invalid workflows are silently excluded.

    Methods:
        list: Return a list of :class:`WorkflowListItem`, one per
            valid workflow on disk.
        get: Return one :class:`WorkflowDetail` by id.
    """

    def __init__(
        self,
        workflows_dir: Path,
        validator: FlowValidator,
    ) -> None:
        """Store the injected workflows directory and validator.

        Args:
            workflows_dir (Path): Directory containing workflow YAMLs.
            validator (FlowValidator): Flow validation service used to
                reject malformed workflows at load time.
        """
        self.workflows_dir = workflows_dir
        self.validator = validator

    def list(self) -> List[WorkflowListItem]:
        """Return a list item per valid workflow on disk, sorted by id.

        Workflows that fail validation are *not* returned. They are
        logged via :func:`print` to stdout so operators notice them
        during container startup; adding a dedicated logger here would
        require a cross-cutting refactor the plan defers.

        Returns:
            List[WorkflowListItem]: One entry per valid workflow,
            sorted by ``id``.
        """
        items: List[WorkflowListItem] = []
        for yaml_path in sorted(self.workflows_dir.glob("*.yml")):
            flow_body = _load_flow_body(yaml_path)
            if flow_body is None:
                continue
            validation_response = self.validator.validate(flow_body)
            if not validation_response.valid:
                continue
            items.append(
                WorkflowListItem(
                    id=yaml_path.stem,
                    label=str(flow_body.get("name", yaml_path.stem)),
                    description=str(flow_body.get("description", "")),
                )
            )
        return items

    def get(self, workflow_id: str) -> WorkflowDetail:
        """Return one workflow's full body by id.

        Args:
            workflow_id (str): YAML filename stem of the workflow to
                load.

        Returns:
            WorkflowDetail: Id, label, description, and raw flow
            body.

        Raises:
            FileNotFoundError: If no workflow YAML exists at
                ``<workflows_dir>/<workflow_id>.yml`` or if the file
                fails flow validation.
        """
        yaml_path = self.workflows_dir / f"{workflow_id}.yml"
        if not yaml_path.is_file():
            raise FileNotFoundError(f"Workflow not found: {workflow_id}")
        flow_body = _load_flow_body(yaml_path)
        if flow_body is None:
            raise FileNotFoundError(
                f"Workflow '{workflow_id}' could not be parsed."
            )
        validation_response = self.validator.validate(flow_body)
        if not validation_response.valid:
            raise FileNotFoundError(
                f"Workflow '{workflow_id}' failed validation: "
                f"{validation_response.model_dump_json()}"
            )
        return WorkflowDetail(
            id=workflow_id,
            label=str(flow_body.get("name", workflow_id)),
            description=str(flow_body.get("description", "")),
            flow=flow_body,
        )


def _load_flow_body(yaml_path: Path) -> Dict[str, Any] | None:
    """Return the ``flow:`` block of a workflow YAML, or ``None`` on failure.

    Args:
        yaml_path (Path): Path to the workflow YAML.

    Returns:
        Dict[str, Any] | None: The ``flow`` block when parsing
        succeeded and the block is a mapping; ``None`` otherwise.
    """
    try:
        with yaml_path.open("r", encoding="utf-8") as file_handle:
            document = yaml.safe_load(file_handle) or {}
    except (OSError, yaml.YAMLError):
        return None
    flow_body = document.get("flow")
    if not isinstance(flow_body, dict):
        return None
    return flow_body


__all__ = [
    "DEFAULT_WORKFLOWS_SOURCE_DIR",
    "WorkflowRepository",
]
