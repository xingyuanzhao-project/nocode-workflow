"""Routes under ``/api/taxonomy`` — taxonomy CRUD.

Contents and relationships
--------------------------

- :data:`router` — :class:`fastapi.APIRouter` exposing:

  - ``GET /api/taxonomy`` — list saved taxonomies.
  - ``POST /api/taxonomy`` — create a new taxonomy.
  - ``GET /api/taxonomy/{taxonomy_id}`` — load one taxonomy.
  - ``PUT /api/taxonomy/{taxonomy_id}`` — update a taxonomy.
  - ``DELETE /api/taxonomy/{taxonomy_id}`` — delete a taxonomy.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.app` mounts :data:`router` at the root.

Invariants enforced by this module
----------------------------------

- Handlers delegate to
  :class:`server.services.taxonomy_repository.TaxonomyRepository`
  and contain no domain logic.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, status

from server.dependencies import get_taxonomy_repository
from server.schemas.taxonomy import (
    TaxonomyListItem,
    TaxonomyResponse,
    TaxonomySaveRequest,
)
from server.services.taxonomy_repository import TaxonomyRepository


router = APIRouter(prefix="/api/taxonomy", tags=["taxonomy"])
"""Router exposing taxonomy CRUD endpoints."""


@router.get("", response_model=List[TaxonomyListItem])
def list_taxonomies(
    repository: TaxonomyRepository = Depends(get_taxonomy_repository),
) -> List[TaxonomyListItem]:
    """Return a DTO list of every saved taxonomy.

    Args:
        repository (TaxonomyRepository): Injected taxonomy repository.

    Returns:
        List[TaxonomyListItem]: One entry per saved taxonomy.
    """
    return repository.list()


@router.post(
    "", response_model=TaxonomyResponse, status_code=status.HTTP_201_CREATED
)
def create_taxonomy(
    request: TaxonomySaveRequest,
    repository: TaxonomyRepository = Depends(get_taxonomy_repository),
) -> TaxonomyResponse:
    """Persist a new taxonomy under a fresh id.

    Args:
        request (TaxonomySaveRequest): Name and taxonomy body.
        repository (TaxonomyRepository): Injected taxonomy repository.

    Returns:
        TaxonomyResponse: The saved taxonomy with its assigned id.
    """
    return repository.save(request)


@router.get("/{taxonomy_id}", response_model=TaxonomyResponse)
def get_taxonomy(
    taxonomy_id: str,
    repository: TaxonomyRepository = Depends(get_taxonomy_repository),
) -> TaxonomyResponse:
    """Load one saved taxonomy by id.

    Args:
        taxonomy_id (str): Taxonomy identifier.
        repository (TaxonomyRepository): Injected taxonomy repository.

    Returns:
        TaxonomyResponse: The loaded taxonomy.
    """
    return repository.get(taxonomy_id)


@router.put("/{taxonomy_id}", response_model=TaxonomyResponse)
def update_taxonomy(
    taxonomy_id: str,
    request: TaxonomySaveRequest,
    repository: TaxonomyRepository = Depends(get_taxonomy_repository),
) -> TaxonomyResponse:
    """Overwrite the JSON at ``taxonomy_id``.

    Args:
        taxonomy_id (str): Taxonomy identifier.
        request (TaxonomySaveRequest): New name and body.
        repository (TaxonomyRepository): Injected taxonomy repository.

    Returns:
        TaxonomyResponse: The saved taxonomy.
    """
    return repository.update(taxonomy_id, request)


@router.delete("/{taxonomy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_taxonomy(
    taxonomy_id: str,
    repository: TaxonomyRepository = Depends(get_taxonomy_repository),
) -> None:
    """Remove the JSON file for ``taxonomy_id``.

    Args:
        taxonomy_id (str): Taxonomy identifier.
        repository (TaxonomyRepository): Injected taxonomy repository.

    Returns:
        None.
    """
    repository.delete(taxonomy_id)
