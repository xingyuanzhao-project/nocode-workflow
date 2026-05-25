"""CRUD over codebook JSON files on disk.

Mirrors the shape of
:class:`server.services.flow_repository.FlowRepository` but operates on
JSON files under :attr:`server.storage.paths.ServerPaths.codebooks_dir`.

Contents and relationships
--------------------------

- :class:`CodebookRepository` — service exposing :meth:`list`,
  :meth:`get`, :meth:`save`, :meth:`update`, and :meth:`delete`.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.routes.codebook` calls these methods from the
  ``/api/codebook`` handlers.

Invariants enforced by this module
----------------------------------

- Codebook ids are derived from the user-supplied name via a slug,
  suffixed with a short hash when the slug alone would collide with an
  existing file.
- Codebooks are stored as JSON (not YAML).
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from server.schemas.codebook import (
    CodebookListItem,
    CodebookResponse,
    CodebookSaveRequest,
)
from server.storage.paths import ServerPaths


_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")
"""Regex used by :func:`_slugify` to collapse non-alphanumeric runs."""


def _slugify(name: str) -> str:
    """Return a filesystem-safe slug derived from ``name``.

    Args:
        name (str): The human-readable name supplied by the user.

    Returns:
        str: Lowercased, hyphen-separated, alphanumeric-only slug.
            Defaults to ``"codebook"`` when ``name`` contains no
            alphanumeric characters.
    """
    slug = _SLUG_PATTERN.sub("-", name.strip().lower()).strip("-")
    return slug or "codebook"


def _short_hash(payload: str) -> str:
    """Return the first 8 hex characters of ``payload``'s SHA-256 digest.

    Args:
        payload (str): The string to hash.

    Returns:
        str: 8-character hexadecimal digest.
    """
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]


def _iso_mtime(path: Path) -> str:
    """Return the file's modification time as an ISO-8601 UTC string.

    Args:
        path (Path): File whose mtime is read.

    Returns:
        str: ISO-8601 string with UTC offset.
    """
    mtime_utc = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return mtime_utc.isoformat()


class CodebookRepository:
    """Service providing CRUD over saved codebook JSONs.

    Attributes:
        paths (ServerPaths): On-disk layout; only
            :attr:`ServerPaths.codebooks_dir` is read.

    Methods:
        list: Return all saved codebooks as
            :class:`server.schemas.codebook.CodebookListItem` entries.
        get: Load one codebook by id.
        save: Persist a codebook under a new id.
        update: Overwrite an existing codebook.
        delete: Remove a codebook from disk.
    """

    def __init__(self, paths: ServerPaths) -> None:
        """Store the injected paths.

        Args:
            paths (ServerPaths): On-disk layout.
        """
        self.paths = paths

    def _path_for(self, codebook_id: str) -> Path:
        """Return the absolute path of the JSON for ``codebook_id``.

        Args:
            codebook_id (str): Identifier returned by :meth:`save`.

        Returns:
            Path: ``<codebooks_dir>/<codebook_id>.json``.
        """
        return self.paths.codebooks_dir / f"{codebook_id}.json"

    def _derive_codebook_id(
        self, name: str, codebook_definition: Dict[str, Any]
    ) -> str:
        """Return a codebook id for ``name`` that does not collide on disk.

        Args:
            name (str): Human-readable codebook name.
            codebook_definition (Dict[str, Any]): Codebook body; hashed
                when the slug alone would collide.

        Returns:
            str: ``<slug>`` when no file exists at that id, otherwise
            ``<slug>-<hash8>``.
        """
        slug = _slugify(name)
        base_path = self._path_for(slug)
        if not base_path.exists():
            return slug
        disambiguator = _short_hash(
            json.dumps(codebook_definition, sort_keys=True)
        )
        return f"{slug}-{disambiguator}"

    def list(self) -> List[CodebookListItem]:
        """Return a DTO list of every codebook JSON on disk.

        Returns:
            List[CodebookListItem]: One entry per saved codebook,
            sorted by id.
        """
        items: List[CodebookListItem] = []
        for json_path in sorted(self.paths.codebooks_dir.glob("*.json")):
            codebook_id = json_path.stem
            try:
                with json_path.open("r", encoding="utf-8") as file_handle:
                    document = json.load(file_handle)
            except (OSError, json.JSONDecodeError):
                continue
            name = (
                document.get("_name")
                if isinstance(document, dict)
                else None
            ) or codebook_id
            items.append(
                CodebookListItem(
                    id=codebook_id,
                    name=str(name),
                    updated_at=_iso_mtime(json_path),
                )
            )
        return items

    def get(self, codebook_id: str) -> CodebookResponse:
        """Load one codebook JSON by id.

        Args:
            codebook_id (str): Identifier returned by :meth:`save`.

        Returns:
            CodebookResponse: The loaded codebook.

        Raises:
            FileNotFoundError: If no JSON exists for ``codebook_id``.
        """
        json_path = self._path_for(codebook_id)
        if not json_path.exists():
            raise FileNotFoundError(f"Codebook not found: {codebook_id}")
        with json_path.open("r", encoding="utf-8") as file_handle:
            document = json.load(file_handle)
        name = (
            document.get("_name")
            if isinstance(document, dict)
            else None
        ) or codebook_id
        return CodebookResponse(
            id=codebook_id,
            name=str(name),
            codebook=document if isinstance(document, dict) else {},
            updated_at=_iso_mtime(json_path),
        )

    def save(self, request: CodebookSaveRequest) -> CodebookResponse:
        """Persist ``request`` under a new codebook id.

        Args:
            request (CodebookSaveRequest): Name and codebook body.

        Returns:
            CodebookResponse: The saved codebook with its assigned id.
        """
        codebook_id = self._derive_codebook_id(request.name, request.codebook)
        return self._write(codebook_id, request)

    def update(
        self, codebook_id: str, request: CodebookSaveRequest
    ) -> CodebookResponse:
        """Overwrite the JSON at ``codebook_id`` with ``request``.

        Args:
            codebook_id (str): Identifier of the codebook to overwrite.
            request (CodebookSaveRequest): New name and codebook body.

        Returns:
            CodebookResponse: The saved codebook with its id echoed
            back.

        Raises:
            FileNotFoundError: If no JSON exists for ``codebook_id``.
        """
        json_path = self._path_for(codebook_id)
        if not json_path.exists():
            raise FileNotFoundError(f"Codebook not found: {codebook_id}")
        return self._write(codebook_id, request)

    def delete(self, codebook_id: str) -> None:
        """Remove the JSON file for ``codebook_id``.

        Args:
            codebook_id (str): Identifier of the codebook to delete.

        Raises:
            FileNotFoundError: If no JSON exists for ``codebook_id``.
        """
        json_path = self._path_for(codebook_id)
        if not json_path.exists():
            raise FileNotFoundError(f"Codebook not found: {codebook_id}")
        json_path.unlink()

    def _write(
        self, codebook_id: str, request: CodebookSaveRequest
    ) -> CodebookResponse:
        """Write ``request`` to disk under ``codebook_id`` and return the DTO.

        Args:
            codebook_id (str): Identifier to write under.
            request (CodebookSaveRequest): Payload to persist.

        Returns:
            CodebookResponse: The saved codebook.
        """
        json_path = self._path_for(codebook_id)
        document = dict(request.codebook)
        document["_name"] = request.name
        with json_path.open("w", encoding="utf-8") as file_handle:
            json.dump(document, file_handle, indent=2, sort_keys=False)
        return CodebookResponse(
            id=codebook_id,
            name=request.name,
            codebook=document,
            updated_at=_iso_mtime(json_path),
        )
