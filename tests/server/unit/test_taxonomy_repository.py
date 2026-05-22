"""Unit tests for :class:`server.services.taxonomy_repository.TaxonomyRepository`.

Covers the create / get / list / update / delete lifecycle. The
taxonomy body is stored as open-shaped JSON so the tests assert the
exact payload round-trips.
"""

from __future__ import annotations

import pytest

from server.schemas.taxonomy import TaxonomySaveRequest
from server.services.taxonomy_repository import TaxonomyRepository


_TAXONOMY_BODY = {
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
def taxonomy_repository(server_paths) -> TaxonomyRepository:
    """Return a :class:`TaxonomyRepository` rooted at the isolated paths."""
    return TaxonomyRepository(paths=server_paths)


class TestTaxonomyRepositoryLifecycle:
    def test_empty_list_when_nothing_saved(
        self, taxonomy_repository: TaxonomyRepository
    ) -> None:
        assert taxonomy_repository.list() == []

    def test_save_get_update_delete_round_trip(
        self, taxonomy_repository: TaxonomyRepository
    ) -> None:
        saved = taxonomy_repository.save(
            TaxonomySaveRequest(name="My Taxonomy", taxonomy=_TAXONOMY_BODY)
        )
        assert saved.id == "my-taxonomy"
        # The repository stores the display name under a private ``_name``
        # key alongside the user-supplied taxonomy body. Tests assert on
        # the caller-visible fields: the original keys round-trip.
        for label_key, label_body in _TAXONOMY_BODY.items():
            assert saved.taxonomy[label_key] == label_body
        assert saved.name == "My Taxonomy"

        fetched = taxonomy_repository.get("my-taxonomy")
        assert fetched.name == "My Taxonomy"
        for label_key, label_body in _TAXONOMY_BODY.items():
            assert fetched.taxonomy[label_key] == label_body

        updated_body = {**_TAXONOMY_BODY}
        updated_body["new_label"] = {
            "definition": "New",
            "options": ["a", "b"],
            "context_definition": "d",
        }
        taxonomy_repository.update(
            "my-taxonomy", TaxonomySaveRequest(name="My Taxonomy", taxonomy=updated_body)
        )
        refetched = taxonomy_repository.get("my-taxonomy")
        assert "new_label" in refetched.taxonomy

        taxonomy_repository.delete("my-taxonomy")
        assert taxonomy_repository.list() == []

    def test_get_unknown_raises_file_not_found(
        self, taxonomy_repository: TaxonomyRepository
    ) -> None:
        with pytest.raises(FileNotFoundError):
            taxonomy_repository.get("ghost")

    def test_delete_unknown_raises_file_not_found(
        self, taxonomy_repository: TaxonomyRepository
    ) -> None:
        with pytest.raises(FileNotFoundError):
            taxonomy_repository.delete("ghost")

    def test_update_unknown_raises_file_not_found(
        self, taxonomy_repository: TaxonomyRepository
    ) -> None:
        with pytest.raises(FileNotFoundError):
            taxonomy_repository.update(
                "ghost",
                TaxonomySaveRequest(name="g", taxonomy=_TAXONOMY_BODY),
            )

    def test_slug_collision_disambiguated(
        self, taxonomy_repository: TaxonomyRepository
    ) -> None:
        first = taxonomy_repository.save(
            TaxonomySaveRequest(name="Collision", taxonomy=_TAXONOMY_BODY)
        )
        second = taxonomy_repository.save(
            TaxonomySaveRequest(
                name="Collision", taxonomy={**_TAXONOMY_BODY, "extra": {"definition": "e"}}
            )
        )
        assert first.id == "collision"
        assert second.id != first.id
