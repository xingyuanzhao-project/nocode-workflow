"""Routes under ``/api/codebook`` — codebook CRUD.

Contents and relationships
--------------------------

- :data:`router` — :class:`fastapi.APIRouter` exposing:

  - ``GET /api/codebook`` — list saved codebooks.
  - ``POST /api/codebook`` — create a new codebook.
  - ``GET /api/codebook/{codebook_id}`` — load one codebook.
  - ``PUT /api/codebook/{codebook_id}`` — update a codebook.
  - ``DELETE /api/codebook/{codebook_id}`` — delete a codebook.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.app` mounts :data:`router` at the root.

Invariants enforced by this module
----------------------------------

- Handlers delegate to
  :class:`server.services.codebook_repository.CodebookRepository`
  and contain no domain logic.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, status

from server.dependencies import get_codebook_repository
from server.schemas.codebook import (
    CodebookListItem,
    CodebookResponse,
    CodebookSaveRequest,
)
from server.services.codebook_repository import CodebookRepository


router = APIRouter(prefix="/api/codebook", tags=["codebook"])
"""Router exposing codebook CRUD endpoints."""


@router.get("", response_model=List[CodebookListItem])
def list_codebooks(
    repository: CodebookRepository = Depends(get_codebook_repository),
) -> List[CodebookListItem]:
    """Return a DTO list of every saved codebook.

    Args:
        repository (CodebookRepository): Injected codebook repository.

    Returns:
        List[CodebookListItem]: One entry per saved codebook.
    """
    return repository.list()


@router.post(
    "", response_model=CodebookResponse, status_code=status.HTTP_201_CREATED
)
def create_codebook(
    request: CodebookSaveRequest,
    repository: CodebookRepository = Depends(get_codebook_repository),
) -> CodebookResponse:
    """Persist a new codebook under a fresh id.

    Args:
        request (CodebookSaveRequest): Name and codebook body.
        repository (CodebookRepository): Injected codebook repository.

    Returns:
        CodebookResponse: The saved codebook with its assigned id.
    """
    return repository.save(request)


@router.get("/{codebook_id}", response_model=CodebookResponse)
def get_codebook(
    codebook_id: str,
    repository: CodebookRepository = Depends(get_codebook_repository),
) -> CodebookResponse:
    """Load one saved codebook by id.

    Args:
        codebook_id (str): Codebook identifier.
        repository (CodebookRepository): Injected codebook repository.

    Returns:
        CodebookResponse: The loaded codebook.
    """
    return repository.get(codebook_id)


@router.put("/{codebook_id}", response_model=CodebookResponse)
def update_codebook(
    codebook_id: str,
    request: CodebookSaveRequest,
    repository: CodebookRepository = Depends(get_codebook_repository),
) -> CodebookResponse:
    """Overwrite the JSON at ``codebook_id``.

    Args:
        codebook_id (str): Codebook identifier.
        request (CodebookSaveRequest): New name and body.
        repository (CodebookRepository): Injected codebook repository.

    Returns:
        CodebookResponse: The saved codebook.
    """
    return repository.update(codebook_id, request)


@router.delete("/{codebook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_codebook(
    codebook_id: str,
    repository: CodebookRepository = Depends(get_codebook_repository),
) -> None:
    """Remove the JSON file for ``codebook_id``.

    Args:
        codebook_id (str): Codebook identifier.
        repository (CodebookRepository): Injected codebook repository.

    Returns:
        None.
    """
    repository.delete(codebook_id)
