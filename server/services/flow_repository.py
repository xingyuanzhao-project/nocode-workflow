"""CRUD over flow YAMLs on disk.

Persists flows under :attr:`server.storage.paths.ServerPaths.flows_dir`
as YAML files named ``<flow_id>.yml``. The on-disk shape matches the
files under ``config/flows/``: a top-level ``flow:`` key whose body is
validated by :class:`src.flow_loader.FlowSchema`.

Contents and relationships
--------------------------

- :class:`FlowRepository` — service exposing :meth:`list`, :meth:`get`,
  :meth:`save`, :meth:`delete`, and :meth:`duplicate`.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.routes.flow` calls these methods from the
  ``/api/flow`` handlers.
- :mod:`server.services.run_dispatcher` does **not** go through this
  repository; it reads saved flows through :meth:`get` only, because
  the dispatcher itself owns the per-run YAML under
  :attr:`server.storage.run_paths.RunPaths.flow_yaml_path`.

Invariants enforced by this module
----------------------------------

- Every flow written to disk is first validated by
  :class:`server.services.flow_validation.FlowValidator`. Invalid
  flows raise :class:`ValueError` and are never persisted.
- Flow identifiers are derived from the user-supplied name via a slug,
  suffixed with an 8-character hash when a collision would otherwise
  overwrite an existing file.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml

from server.schemas.flow import (
    FlowGetResponse,
    FlowListItem,
    FlowSaveRequest,
    FlowSaveResponse,
)
from server.services.flow_validation import FlowValidator
from server.storage.paths import ServerPaths


_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")
"""Regex used by :func:`_slugify` to collapse non-alphanumeric runs."""


def _slugify(name: str) -> str:
    """Return a filesystem-safe slug derived from ``name``.

    Args:
        name (str): The human-readable name supplied by the user.

    Returns:
        str: Lowercased, hyphen-separated, alphanumeric-only slug.
            Defaults to ``"flow"`` when ``name`` contains no
            alphanumeric characters.
    """
    slug = _SLUG_PATTERN.sub("-", name.strip().lower()).strip("-")
    return slug or "flow"


def _short_hash(payload: str) -> str:
    """Return the first 8 hex characters of ``payload``'s SHA-256 digest.

    Used to disambiguate flow identifiers when two names slugify the
    same way.

    Args:
        payload (str): The string to hash.

    Returns:
        str: 8-character hexadecimal digest.
    """
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]


class FlowRepository:
    """Service providing CRUD over saved flow YAMLs.

    Attributes:
        paths (ServerPaths): On-disk layout; only
            :attr:`ServerPaths.flows_dir` is read.
        validator (FlowValidator): Used to validate every flow before
            writing.

    Methods:
        list: Return all saved flows as
            :class:`server.schemas.flow.FlowListItem` entries.
        get: Load one flow by id and return its
            :class:`server.schemas.flow.FlowGetResponse`.
        save: Validate and write a flow, returning its
            :class:`server.schemas.flow.FlowSaveResponse`.
        update: Validate and overwrite a flow under an existing id.
        delete: Remove a flow from disk.
        duplicate: Copy an existing flow under a new id.
    """

    def __init__(self, paths: ServerPaths, validator: FlowValidator) -> None:
        """Store the injected paths and validator.

        Args:
            paths (ServerPaths): On-disk layout.
            validator (FlowValidator): Flow validation service.
        """
        self.paths = paths
        self.validator = validator

    def _path_for(self, flow_id: str) -> Path:
        """Return the absolute path of the YAML for ``flow_id``.

        Args:
            flow_id (str): Identifier returned by :meth:`save`.

        Returns:
            Path: ``<flows_dir>/<flow_id>.yml``.
        """
        return self.paths.flows_dir / f"{flow_id}.yml"

    def _derive_flow_id(self, name: str, flow_definition: Dict[str, Any]) -> str:
        """Return a flow id for ``name`` that does not collide on disk.

        Args:
            name (str): Human-readable flow name.
            flow_definition (Dict[str, Any]): Flow body; hashed when the
                slug alone would collide with an existing file.

        Returns:
            str: ``<slug>`` when no file exists at that id, otherwise
            ``<slug>-<hash8>``.
        """
        slug = _slugify(name)
        base_path = self._path_for(slug)
        if not base_path.exists():
            return slug
        disambiguator = _short_hash(
            yaml.safe_dump(flow_definition, sort_keys=True)
        )
        return f"{slug}-{disambiguator}"

    @staticmethod
    def _document_for(name: str, flow_definition: Dict[str, Any]) -> Dict[str, Any]:
        """Compose the on-disk YAML document from ``name`` and ``flow_definition``.

        Injects ``name`` into the flow body under the ``flow.name`` key
        so the value the user supplies via the HTTP API is preserved
        when :class:`src.flow_loader.FlowSchema` loads the file.

        Args:
            name (str): Human-readable flow name.
            flow_definition (Dict[str, Any]): Flow body.

        Returns:
            Dict[str, Any]: ``{"flow": {..., "name": name}}``.
        """
        flow_body = dict(flow_definition)
        flow_body["name"] = name
        return {"flow": flow_body}

    def list(self) -> List[FlowListItem]:
        """Return a DTO list of every flow YAML on disk.

        Returns:
            List[FlowListItem]: One entry per saved flow, sorted by id.
        """
        items: List[FlowListItem] = []
        for yaml_path in sorted(self.paths.flows_dir.glob("*.yml")):
            flow_id = yaml_path.stem
            try:
                with yaml_path.open("r", encoding="utf-8") as file_handle:
                    document = yaml.safe_load(file_handle) or {}
            except (OSError, yaml.YAMLError):
                continue
            flow_body = document.get("flow", {}) or {}
            items.append(
                FlowListItem(
                    id=flow_id,
                    name=str(flow_body.get("name", flow_id)),
                    description=str(flow_body.get("description", "")),
                    updated_at=_iso_mtime(yaml_path),
                )
            )
        return items

    def get(self, flow_id: str) -> FlowGetResponse:
        """Load one flow YAML by id.

        Args:
            flow_id (str): Identifier returned by :meth:`save`.

        Returns:
            FlowGetResponse: The loaded flow.

        Raises:
            FileNotFoundError: If no YAML exists for ``flow_id``.
        """
        yaml_path = self._path_for(flow_id)
        if not yaml_path.exists():
            raise FileNotFoundError(f"Flow not found: {flow_id}")
        with yaml_path.open("r", encoding="utf-8") as file_handle:
            document = yaml.safe_load(file_handle) or {}
        flow_body = document.get("flow", {}) or {}
        return FlowGetResponse(
            id=flow_id,
            name=str(flow_body.get("name", flow_id)),
            flow=flow_body,
            updated_at=_iso_mtime(yaml_path),
        )

    def save(self, request: FlowSaveRequest) -> FlowSaveResponse:
        """Validate ``request`` and persist it under a new flow id.

        Args:
            request (FlowSaveRequest): Name and flow body to save.

        Returns:
            FlowSaveResponse: The assigned id and absolute path.

        Raises:
            ValueError: If the flow fails validation.
        """
        validation_response = self.validator.validate(request.flow)
        if not validation_response.valid:
            raise ValueError(validation_response.model_dump_json())
        flow_id = self._derive_flow_id(request.name, request.flow)
        yaml_path = self._path_for(flow_id)
        document = self._document_for(request.name, request.flow)
        with yaml_path.open("w", encoding="utf-8") as file_handle:
            yaml.safe_dump(document, file_handle, sort_keys=False)
        return FlowSaveResponse(id=flow_id, path=str(yaml_path))

    def update(self, flow_id: str, request: FlowSaveRequest) -> FlowSaveResponse:
        """Validate ``request`` and overwrite the YAML at ``flow_id``.

        Args:
            flow_id (str): Identifier of the flow to overwrite.
            request (FlowSaveRequest): New name and flow body.

        Returns:
            FlowSaveResponse: ``flow_id`` echoed back with the path.

        Raises:
            FileNotFoundError: If no YAML exists for ``flow_id``.
            ValueError: If the new flow fails validation.
        """
        yaml_path = self._path_for(flow_id)
        if not yaml_path.exists():
            raise FileNotFoundError(f"Flow not found: {flow_id}")
        validation_response = self.validator.validate(request.flow)
        if not validation_response.valid:
            raise ValueError(validation_response.model_dump_json())
        document = self._document_for(request.name, request.flow)
        with yaml_path.open("w", encoding="utf-8") as file_handle:
            yaml.safe_dump(document, file_handle, sort_keys=False)
        return FlowSaveResponse(id=flow_id, path=str(yaml_path))

    def delete(self, flow_id: str) -> None:
        """Remove the YAML file for ``flow_id`` from disk.

        Args:
            flow_id (str): Identifier of the flow to delete.

        Raises:
            FileNotFoundError: If no YAML exists for ``flow_id``.
        """
        yaml_path = self._path_for(flow_id)
        if not yaml_path.exists():
            raise FileNotFoundError(f"Flow not found: {flow_id}")
        yaml_path.unlink()

    def duplicate(self, flow_id: str, new_name: str) -> FlowSaveResponse:
        """Copy an existing flow under a new name and id.

        Args:
            flow_id (str): Identifier of the flow to copy.
            new_name (str): Name for the new copy.

        Returns:
            FlowSaveResponse: Id and absolute path of the new copy.

        Raises:
            FileNotFoundError: If the source flow does not exist.
        """
        source = self.get(flow_id)
        return self.save(FlowSaveRequest(name=new_name, flow=source.flow))


def _iso_mtime(path: Path) -> str:
    """Return the file's modification time as an ISO-8601 UTC string.

    Args:
        path (Path): File whose mtime is read.

    Returns:
        str: ISO-8601 string with UTC offset.
    """
    mtime_utc = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return mtime_utc.isoformat()
