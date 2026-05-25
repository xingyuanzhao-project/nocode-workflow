"""Unit tests for :class:`server.services.codebook_repository.CodebookRepository`.

Covers the create / get / list / update / delete lifecycle. The
codebook body is stored as open-shaped JSON so the tests assert the
exact payload round-trips.
"""

from __future__ import annotations

import pytest

from server.schemas.codebook import CodebookSaveRequest
from server.services.codebook_repository import CodebookRepository


_CODEBOOK_BODY = {
    "desenlace": {
        "definition": "Outcome of the event",
        "options": ["muerte", "herido", "ileso"],
        "context_definition": "Pick the outcome reported for the victim.",
    },
    "grupo_social": {
        "definition": "Social group",
        "options": ["campesino", "indigena", "estudiante"],
        "context_definition": "Pick the social group the victim belongs to.",
    },
}


@pytest.fixture
def codebook_repository(server_paths) -> CodebookRepository:
    """Return a :class:`CodebookRepository` rooted at the isolated paths."""
    return CodebookRepository(paths=server_paths)


class TestCodebookRepositoryLifecycle:
    def test_empty_list_when_nothing_saved(
        self, codebook_repository: CodebookRepository
    ) -> None:
        assert codebook_repository.list() == []

    def test_save_get_update_delete_round_trip(
        self, codebook_repository: CodebookRepository
    ) -> None:
        saved = codebook_repository.save(
            CodebookSaveRequest(name="My Codebook", codebook=_CODEBOOK_BODY)
        )
        assert saved.id == "my-codebook"
        for label_key, label_body in _CODEBOOK_BODY.items():
            assert saved.codebook[label_key] == label_body
        assert saved.name == "My Codebook"

        fetched = codebook_repository.get("my-codebook")
        assert fetched.name == "My Codebook"
        for label_key, label_body in _CODEBOOK_BODY.items():
            assert fetched.codebook[label_key] == label_body

        updated_body = {**_CODEBOOK_BODY}
        updated_body["new_label"] = {
            "definition": "New",
            "options": ["a", "b"],
            "context_definition": "d",
        }
        codebook_repository.update(
            "my-codebook", CodebookSaveRequest(name="My Codebook", codebook=updated_body)
        )
        refetched = codebook_repository.get("my-codebook")
        assert "new_label" in refetched.codebook

        codebook_repository.delete("my-codebook")
        assert codebook_repository.list() == []

    def test_get_unknown_raises_file_not_found(
        self, codebook_repository: CodebookRepository
    ) -> None:
        with pytest.raises(FileNotFoundError):
            codebook_repository.get("ghost")

    def test_delete_unknown_raises_file_not_found(
        self, codebook_repository: CodebookRepository
    ) -> None:
        with pytest.raises(FileNotFoundError):
            codebook_repository.delete("ghost")

    def test_update_unknown_raises_file_not_found(
        self, codebook_repository: CodebookRepository
    ) -> None:
        with pytest.raises(FileNotFoundError):
            codebook_repository.update(
                "ghost",
                CodebookSaveRequest(name="g", codebook=_CODEBOOK_BODY),
            )

    def test_slug_collision_disambiguated(
        self, codebook_repository: CodebookRepository
    ) -> None:
        first = codebook_repository.save(
            CodebookSaveRequest(name="Collision", codebook=_CODEBOOK_BODY)
        )
        second = codebook_repository.save(
            CodebookSaveRequest(
                name="Collision", codebook={**_CODEBOOK_BODY, "extra": {"definition": "e"}}
            )
        )
        assert first.id == "collision"
        assert second.id != first.id
