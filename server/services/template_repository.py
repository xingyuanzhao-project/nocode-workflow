"""Read-only repository of preset flow templates shipped with the app.

Templates live on disk under ``<project_root>/config/templates/*.yml``
and are read-only: they ship with the repository, not with user data.
The GUI's "New Flow" dialog queries this repository to render its
template list, and then fetches the full body when the user picks one.

Contents and relationships
--------------------------

- :class:`TemplateRepository` — the service; exposes
  :meth:`list` (list-view) and :meth:`get` (detail-view).
- :data:`_PROJECT_ROOT` — project root derived from this file's
  location; mirrors the same convention used by
  :mod:`server.storage.paths`.
- :data:`DEFAULT_TEMPLATES_DIR` — canonical templates directory
  (``<project_root>/config/templates``). Tests can inject a different
  directory at construction time.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.routes.templates` calls :meth:`list` and :meth:`get`.
- :mod:`server.dependencies` provides the repository instance via
  ``request.app.state.template_repository``, constructed once in
  :func:`server.app.create_app`.

Invariants enforced by this module
----------------------------------

- Every template YAML is validated by
  :class:`server.services.flow_validation.FlowValidator` at load time.
  A template that fails validation is *excluded* from :meth:`list` and
  raises :class:`FileNotFoundError` (via :meth:`get`) when requested,
  so the GUI can never render a broken template onto the canvas.
- Template ids are the YAML filename stems; filenames must therefore be
  stable (renaming a template changes its id).
- The repository is read-only. There is no :meth:`save`; templates are
  managed via the git repository, not the HTTP API.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import yaml

from server.schemas.templates import FlowTemplateDetail, FlowTemplateListItem
from server.services.flow_validation import FlowValidator


_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
"""Project root derived from this file's location.

Used only to compute :data:`DEFAULT_TEMPLATES_DIR`. Matches the same
derivation used in :mod:`server.storage.paths`.
"""


DEFAULT_TEMPLATES_DIR: Path = _PROJECT_ROOT / "config" / "templates"
"""Canonical on-disk location of the template YAMLs.

The container workflow mounts ``./config`` into ``/app/config``, so
this resolves correctly both on the host (development) and inside the
worker and web containers.
"""


class TemplateRepository:
    """Read-only repository of preset flow templates.

    Attributes:
        templates_dir (Path): Directory containing the template YAMLs.
        validator (FlowValidator): Used to verify every template loads
            cleanly; invalid templates are silently excluded.

    Methods:
        list: Return a list of :class:`FlowTemplateListItem`, one per
            valid template on disk.
        get: Return one :class:`FlowTemplateDetail` by id.
    """

    def __init__(
        self,
        templates_dir: Path,
        validator: FlowValidator,
    ) -> None:
        """Store the injected templates directory and validator.

        Args:
            templates_dir (Path): Directory containing template YAMLs.
            validator (FlowValidator): Flow validation service used to
                reject malformed templates at load time.
        """
        self.templates_dir = templates_dir
        self.validator = validator

    def list(self) -> List[FlowTemplateListItem]:
        """Return a list item per valid template on disk, sorted by id.

        Templates that fail validation are *not* returned. They are
        logged via :func:`print` to stdout so operators notice them
        during container startup; adding a dedicated logger here would
        require a cross-cutting refactor the plan defers.

        Returns:
            List[FlowTemplateListItem]: One entry per valid template,
            sorted by ``id``.
        """
        items: List[FlowTemplateListItem] = []
        for yaml_path in sorted(self.templates_dir.glob("*.yml")):
            flow_body = _load_flow_body(yaml_path)
            if flow_body is None:
                continue
            validation_response = self.validator.validate(flow_body)
            if not validation_response.valid:
                continue
            items.append(
                FlowTemplateListItem(
                    id=yaml_path.stem,
                    label=str(flow_body.get("name", yaml_path.stem)),
                    description=str(flow_body.get("description", "")),
                )
            )
        return items

    def get(self, template_id: str) -> FlowTemplateDetail:
        """Return one template's full body by id.

        Args:
            template_id (str): YAML filename stem of the template to
                load.

        Returns:
            FlowTemplateDetail: Id, label, description, and raw flow
            body.

        Raises:
            FileNotFoundError: If no template YAML exists at
                ``<templates_dir>/<template_id>.yml`` or if the file
                fails flow validation.
        """
        yaml_path = self.templates_dir / f"{template_id}.yml"
        if not yaml_path.is_file():
            raise FileNotFoundError(f"Flow template not found: {template_id}")
        flow_body = _load_flow_body(yaml_path)
        if flow_body is None:
            raise FileNotFoundError(
                f"Flow template '{template_id}' could not be parsed."
            )
        validation_response = self.validator.validate(flow_body)
        if not validation_response.valid:
            raise FileNotFoundError(
                f"Flow template '{template_id}' failed validation: "
                f"{validation_response.model_dump_json()}"
            )
        return FlowTemplateDetail(
            id=template_id,
            label=str(flow_body.get("name", template_id)),
            description=str(flow_body.get("description", "")),
            flow=flow_body,
        )


def _load_flow_body(yaml_path: Path) -> Dict[str, Any] | None:
    """Return the ``flow:`` block of a template YAML, or ``None`` on failure.

    Args:
        yaml_path (Path): Path to the template YAML.

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
    "DEFAULT_TEMPLATES_DIR",
    "TemplateRepository",
]
