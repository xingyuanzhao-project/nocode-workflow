"""Unit tests for :class:`server.services.prompts_repository.PromptsRepository`.

Covers the happy path against the real ``config/prompts.json``, the
missing-file error branch, and the non-object-top-level error branch.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from server.services.prompts_repository import (
    DEFAULT_PROMPTS_PATH,
    DEFAULT_PROMPTS_RELATIVE_POSIX,
    PromptsRepository,
)


class TestDefaultPromptsFile:
    def test_reads_every_documented_key(self) -> None:
        repository = PromptsRepository()
        response = repository.read()
        assert response.path == DEFAULT_PROMPTS_RELATIVE_POSIX
        # Core keys every flow template references.
        for required_key in [
            "summary",
            "summary_first",
            "summary_update",
            "classification",
            "label_spans_extract",
            "label_summary_first",
            "label_summary_update",
            "label_synthesis",
        ]:
            assert required_key in response.prompts


class TestPromptsRepositoryErrors:
    def test_missing_file_raises_file_not_found(self, tmp_path: Path) -> None:
        repository = PromptsRepository(
            prompts_path=tmp_path / "missing.json",
            relative_posix_path="nope.json",
        )
        with pytest.raises(FileNotFoundError):
            repository.read()

    def test_non_object_top_level_raises_value_error(self, tmp_path: Path) -> None:
        payload_path = tmp_path / "list.json"
        payload_path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
        repository = PromptsRepository(
            prompts_path=payload_path, relative_posix_path="list.json"
        )
        with pytest.raises(ValueError, match="must be a JSON object"):
            repository.read()

    def test_empty_object_is_allowed(self, tmp_path: Path) -> None:
        payload_path = tmp_path / "empty.json"
        payload_path.write_text("{}", encoding="utf-8")
        repository = PromptsRepository(
            prompts_path=payload_path, relative_posix_path="empty.json"
        )
        response = repository.read()
        assert response.prompts == {}
