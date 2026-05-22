"""HTTP DTOs for the taxonomy CRUD endpoints.

Mirrors the shape used by :class:`server.services.taxonomy_repository.TaxonomyRepository`.
The taxonomy JSON body is kept as a raw :class:`dict`; the service layer
is responsible for shape validation.

Contents and relationships
--------------------------

- :class:`TaxonomySaveRequest` / :class:`TaxonomyResponse` — payload and
  response for taxonomy create/update/get.
- :class:`TaxonomyListItem` — per-entry shape returned by
  ``GET /api/taxonomy``.

How the rest of the system uses this module
-------------------------------------------

- :class:`server.services.taxonomy_repository.TaxonomyRepository` reads
  :class:`TaxonomySaveRequest` payloads and returns
  :class:`TaxonomyResponse` / :class:`TaxonomyListItem` instances.
"""

from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, ConfigDict


class TaxonomySaveRequest(BaseModel):
    """Body of ``POST /api/taxonomy`` and ``PUT /api/taxonomy/{id}``.

    Attributes:
        name (str): Human-readable taxonomy name. Also used as the seed
            for the derived ``taxonomy_id`` slug on create.
        taxonomy (Dict[str, Any]): Raw taxonomy JSON payload.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    taxonomy: Dict[str, Any]


class TaxonomyResponse(BaseModel):
    """Response of taxonomy create/update/get endpoints.

    Attributes:
        id (str): Taxonomy identifier.
        name (str): Human-readable taxonomy name.
        taxonomy (Dict[str, Any]): Raw taxonomy JSON payload.
        updated_at (str): ISO-8601 timestamp of the JSON file's last
            modification.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    taxonomy: Dict[str, Any]
    updated_at: str


class TaxonomyListItem(BaseModel):
    """One entry in the response of ``GET /api/taxonomy``.

    Attributes:
        id (str): Taxonomy identifier.
        name (str): Human-readable taxonomy name.
        updated_at (str): ISO-8601 timestamp of the JSON file's last
            modification.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    updated_at: str
