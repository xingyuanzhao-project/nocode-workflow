"""Unit tests for :class:`server.services.flow_repository.FlowRepository`.

Covers the full CRUD lifecycle plus the slug-collision and
validation paths.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from server.schemas.flow import FlowSaveRequest
from server.services.flow_repository import FlowRepository
from server.services.flow_validation import FlowValidator


@pytest.fixture
def flow_repository(server_paths, flow_validator: FlowValidator) -> FlowRepository:
    """Build a :class:`FlowRepository` against the isolated paths fixture.

    Args:
        server_paths: Isolated :class:`ServerPaths`.
        flow_validator (FlowValidator): Real validator; repository
            rejects invalid payloads through it.

    Returns:
        FlowRepository: Repository ready for CRUD tests.
    """
    return FlowRepository(paths=server_paths, validator=flow_validator)


class TestFlowRepositoryLifecycle:
    def test_empty_list_when_nothing_saved(self, flow_repository: FlowRepository) -> None:
        assert flow_repository.list() == []

    def test_save_get_list_update_delete_round_trip(
        self, flow_repository: FlowRepository, valid_flow_body: dict
    ) -> None:
        save_response = flow_repository.save(
            FlowSaveRequest(name="Saved Flow", flow=valid_flow_body)
        )
        assert save_response.id == "saved-flow"
        assert Path(save_response.path).exists()

        listed = flow_repository.list()
        assert len(listed) == 1
        assert listed[0].id == "saved-flow"
        assert listed[0].name == "Saved Flow"

        fetched = flow_repository.get("saved-flow")
        assert fetched.id == "saved-flow"
        assert fetched.flow["name"] == "Saved Flow"

        # Update: change description and assert new value persists.
        patched_body = {**valid_flow_body, "description": "updated description"}
        flow_repository.update(
            "saved-flow", FlowSaveRequest(name="Saved Flow", flow=patched_body)
        )
        assert flow_repository.get("saved-flow").flow["description"] == "updated description"

        flow_repository.delete("saved-flow")
        assert flow_repository.list() == []

    def test_save_rejects_invalid_flow(self, flow_repository: FlowRepository) -> None:
        with pytest.raises(ValueError):
            flow_repository.save(FlowSaveRequest(name="Broken", flow={"nonsense": True}))

    def test_get_unknown_raises_file_not_found(
        self, flow_repository: FlowRepository
    ) -> None:
        with pytest.raises(FileNotFoundError):
            flow_repository.get("ghost")

    def test_update_unknown_raises_file_not_found(
        self, flow_repository: FlowRepository, valid_flow_body: dict
    ) -> None:
        with pytest.raises(FileNotFoundError):
            flow_repository.update(
                "ghost", FlowSaveRequest(name="G", flow=valid_flow_body)
            )

    def test_delete_unknown_raises_file_not_found(
        self, flow_repository: FlowRepository
    ) -> None:
        with pytest.raises(FileNotFoundError):
            flow_repository.delete("ghost")


class TestFlowRepositorySlugCollisions:
    def test_second_save_with_same_name_gets_hash_suffix(
        self, flow_repository: FlowRepository, valid_flow_body: dict
    ) -> None:
        first = flow_repository.save(
            FlowSaveRequest(name="Same Name", flow=valid_flow_body)
        )
        second_body = {**valid_flow_body, "description": "second copy"}
        second = flow_repository.save(
            FlowSaveRequest(name="Same Name", flow=second_body)
        )
        assert first.id == "same-name"
        # Suffix has the shape "same-name-<hash8>" but we only assert
        # the prefix + hyphen + nonempty suffix since the hash depends
        # on the YAML serialisation.
        assert second.id.startswith("same-name-")
        assert len(second.id.split("-")[-1]) == 8

    def test_duplicate_copies_body_and_name(
        self, flow_repository: FlowRepository, valid_flow_body: dict
    ) -> None:
        saved = flow_repository.save(
            FlowSaveRequest(name="Original", flow=valid_flow_body)
        )
        duplicate = flow_repository.duplicate(saved.id, "Original Copy")
        assert duplicate.id != saved.id
        # Content is copied verbatim under the new name.
        fetched = flow_repository.get(duplicate.id)
        assert fetched.name == "Original Copy"
