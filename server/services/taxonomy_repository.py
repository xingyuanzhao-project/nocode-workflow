"""CRUD over taxonomy JSON files on disk.

Mirrors the shape of
:class:`server.services.flow_repository.FlowRepository` but operates on
JSON files under :attr:`server.storage.paths.ServerPaths.taxonomies_dir`.

Contents and relationships
--------------------------

- :class:`TaxonomyRepository` — service exposing :meth:`list`,
  :meth:`get`, :meth:`save`, :meth:`update`, and :meth:`delete`.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.routes.taxonomy` calls these methods from the
  ``/api/taxonomy`` handlers.

Invariants enforced by this module
----------------------------------

- Taxonomy ids are derived from the user-supplied name via a slug,
  suffixed with a short hash when the slug alone would collide with an
  existing file.
- Taxonomies are stored as JSON (not YAML) to match the existing
  ``config/taxonomy.json`` format consumed by the processors.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from server.schemas.taxonomy import (
    TaxonomyListItem,
    TaxonomyResponse,
    TaxonomySaveRequest,
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
            Defaults to ``"taxonomy"`` when ``name`` contains no
            alphanumeric characters.
    """
    slug = _SLUG_PATTERN.sub("-", name.strip().lower()).strip("-")
    return slug or "taxonomy"


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


class TaxonomyRepository:
    """Service providing CRUD over saved taxonomy JSONs.

    Attributes:
        paths (ServerPaths): On-disk layout; only
            :attr:`ServerPaths.taxonomies_dir` is read.

    Methods:
        list: Return all saved taxonomies as
            :class:`server.schemas.taxonomy.TaxonomyListItem` entries.
        get: Load one taxonomy by id.
        save: Persist a taxonomy under a new id.
        update: Overwrite an existing taxonomy.
        delete: Remove a taxonomy from disk.
    """

    def __init__(self, paths: ServerPaths) -> None:
        """Store the injected paths.

        Args:
            paths (ServerPaths): On-disk layout.
        """
        self.paths = paths

    def _path_for(self, taxonomy_id: str) -> Path:
        """Return the absolute path of the JSON for ``taxonomy_id``.

        Args:
            taxonomy_id (str): Identifier returned by :meth:`save`.

        Returns:
            Path: ``<taxonomies_dir>/<taxonomy_id>.json``.
        """
        return self.paths.taxonomies_dir / f"{taxonomy_id}.json"

    def _derive_taxonomy_id(
        self, name: str, taxonomy_definition: Dict[str, Any]
    ) -> str:
        """Return a taxonomy id for ``name`` that does not collide on disk.

        Args:
            name (str): Human-readable taxonomy name.
            taxonomy_definition (Dict[str, Any]): Taxonomy body; hashed
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
            json.dumps(taxonomy_definition, sort_keys=True)
        )
        return f"{slug}-{disambiguator}"

    def list(self) -> List[TaxonomyListItem]:
        """Return a DTO list of every taxonomy JSON on disk.

        Returns:
            List[TaxonomyListItem]: One entry per saved taxonomy,
            sorted by id.
        """
        items: List[TaxonomyListItem] = []
        for json_path in sorted(self.paths.taxonomies_dir.glob("*.json")):
            taxonomy_id = json_path.stem
            try:
                with json_path.open("r", encoding="utf-8") as file_handle:
                    document = json.load(file_handle)
            except (OSError, json.JSONDecodeError):
                continue
            name = (
                document.get("_name")
                if isinstance(document, dict)
                else None
            ) or taxonomy_id
            items.append(
                TaxonomyListItem(
                    id=taxonomy_id,
                    name=str(name),
                    updated_at=_iso_mtime(json_path),
                )
            )
        return items

    def get(self, taxonomy_id: str) -> TaxonomyResponse:
        """Load one taxonomy JSON by id.

        Args:
            taxonomy_id (str): Identifier returned by :meth:`save`.

        Returns:
            TaxonomyResponse: The loaded taxonomy.

        Raises:
            FileNotFoundError: If no JSON exists for ``taxonomy_id``.
        """
        json_path = self._path_for(taxonomy_id)
        if not json_path.exists():
            raise FileNotFoundError(f"Taxonomy not found: {taxonomy_id}")
        with json_path.open("r", encoding="utf-8") as file_handle:
            document = json.load(file_handle)
        name = (
            document.get("_name")
            if isinstance(document, dict)
            else None
        ) or taxonomy_id
        return TaxonomyResponse(
            id=taxonomy_id,
            name=str(name),
            taxonomy=document if isinstance(document, dict) else {},
            updated_at=_iso_mtime(json_path),
        )

    def save(self, request: TaxonomySaveRequest) -> TaxonomyResponse:
        """Persist ``request`` under a new taxonomy id.

        Args:
            request (TaxonomySaveRequest): Name and taxonomy body.

        Returns:
            TaxonomyResponse: The saved taxonomy with its assigned id.
        """
        taxonomy_id = self._derive_taxonomy_id(request.name, request.taxonomy)
        return self._write(taxonomy_id, request)

    def update(
        self, taxonomy_id: str, request: TaxonomySaveRequest
    ) -> TaxonomyResponse:
        """Overwrite the JSON at ``taxonomy_id`` with ``request``.

        Args:
            taxonomy_id (str): Identifier of the taxonomy to overwrite.
            request (TaxonomySaveRequest): New name and taxonomy body.

        Returns:
            TaxonomyResponse: The saved taxonomy with its id echoed
            back.

        Raises:
            FileNotFoundError: If no JSON exists for ``taxonomy_id``.
        """
        json_path = self._path_for(taxonomy_id)
        if not json_path.exists():
            raise FileNotFoundError(f"Taxonomy not found: {taxonomy_id}")
        return self._write(taxonomy_id, request)

    def delete(self, taxonomy_id: str) -> None:
        """Remove the JSON file for ``taxonomy_id``.

        Args:
            taxonomy_id (str): Identifier of the taxonomy to delete.

        Raises:
            FileNotFoundError: If no JSON exists for ``taxonomy_id``.
        """
        json_path = self._path_for(taxonomy_id)
        if not json_path.exists():
            raise FileNotFoundError(f"Taxonomy not found: {taxonomy_id}")
        json_path.unlink()

    def _write(
        self, taxonomy_id: str, request: TaxonomySaveRequest
    ) -> TaxonomyResponse:
        """Write ``request`` to disk under ``taxonomy_id`` and return the DTO.

        Args:
            taxonomy_id (str): Identifier to write under.
            request (TaxonomySaveRequest): Payload to persist.

        Returns:
            TaxonomyResponse: The saved taxonomy.
        """
        json_path = self._path_for(taxonomy_id)
        document = dict(request.taxonomy)
        document["_name"] = request.name
        with json_path.open("w", encoding="utf-8") as file_handle:
            json.dump(document, file_handle, indent=2, sort_keys=False)
        return TaxonomyResponse(
            id=taxonomy_id,
            name=request.name,
            taxonomy=document,
            updated_at=_iso_mtime(json_path),
        )
