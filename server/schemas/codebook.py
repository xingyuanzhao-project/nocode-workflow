"""HTTP DTOs for the codebook CRUD endpoints.

Mirrors the shape used by :class:`server.services.codebook_repository.CodebookRepository`.
The codebook JSON body is kept as a raw :class:`dict`; the service layer
is responsible for shape validation.

Contents and relationships
--------------------------

- :class:`CodebookSaveRequest` / :class:`CodebookResponse` — payload and
  response for codebook create/update/get.
- :class:`CodebookListItem` — per-entry shape returned by
  ``GET /api/codebook``.

How the rest of the system uses this module
-------------------------------------------

- :class:`server.services.codebook_repository.CodebookRepository` reads
  :class:`CodebookSaveRequest` payloads and returns
  :class:`CodebookResponse` / :class:`CodebookListItem` instances.
"""

from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, ConfigDict


class CodebookSaveRequest(BaseModel):
    """Body of ``POST /api/codebook`` and ``PUT /api/codebook/{id}``.

    Attributes:
        name (str): Human-readable codebook name. Also used as the seed
            for the derived ``codebook_id`` slug on create.
        codebook (Dict[str, Any]): Raw codebook JSON payload.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    codebook: Dict[str, Any]


class CodebookResponse(BaseModel):
    """Response of codebook create/update/get endpoints.

    Attributes:
        id (str): Codebook identifier.
        name (str): Human-readable codebook name.
        codebook (Dict[str, Any]): Raw codebook JSON payload.
        updated_at (str): ISO-8601 timestamp of the JSON file's last
            modification.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    codebook: Dict[str, Any]
    updated_at: str


class CodebookListItem(BaseModel):
    """One entry in the response of ``GET /api/codebook``.

    Attributes:
        id (str): Codebook identifier.
        name (str): Human-readable codebook name.
        updated_at (str): ISO-8601 timestamp of the JSON file's last
            modification.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    updated_at: str
