"""Read-only repository exposing ``config/prompts.json`` over HTTP.

The prompts file is checked into the repository alongside
``workflows/node_types.yaml`` and the flow templates. This service reads
the file once per request and returns a typed DTO so the GUI can
populate its Prompt tab without re-parsing the raw JSON in the
browser.

Contents and relationships
--------------------------

- :class:`PromptsRepository` — the service.
- :data:`_PROJECT_ROOT` — project root derived from this file's
  location.
- :data:`DEFAULT_PROMPTS_PATH` — canonical on-disk path of the prompts
  JSON (``<project_root>/config/prompts.json``).

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.routes.prompts` calls :meth:`PromptsRepository.read`
  from ``GET /api/prompts``.
- :mod:`server.dependencies` provides the singleton via
  ``request.app.state.prompts_repository``, constructed once in
  :func:`server.app.create_app`.

Invariants enforced by this module
----------------------------------

- The repository is read-only; the prompts file is managed via the
  git repository, not the HTTP API. Writing prompts would require a
  separate PUT endpoint and permission model.
- The returned :attr:`PromptsResponse.path` is always a
  project-root-relative POSIX string, matching the convention in
  :mod:`server.storage.paths`. Host and container resolve it to the
  same bytes on disk.
"""

from __future__ import annotations

import json
from pathlib import Path

from server.schemas.prompts import PromptEntry, PromptsResponse


_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
"""Project root derived from this file's location.

Matches the derivation used in :mod:`server.storage.paths` and
:mod:`server.services.template_repository`.
"""


DEFAULT_PROMPTS_PATH: Path = _PROJECT_ROOT / "config" / "prompts.json"
"""Canonical on-disk location of the prompts JSON."""


DEFAULT_PROMPTS_RELATIVE_POSIX: str = "config/prompts.json"
"""Project-root-relative POSIX form of :data:`DEFAULT_PROMPTS_PATH`.

Returned verbatim in :attr:`server.schemas.prompts.PromptsResponse.path`
so GUI clients can paste it into a flow's ``prompts_ref`` field as
``"config/prompts.json::<key>"``.
"""


class PromptsRepository:
    """Read-only repository exposing ``config/prompts.json``.

    Attributes:
        prompts_path (Path): Absolute path to the prompts JSON on disk.
        relative_posix_path (str): :attr:`prompts_path` expressed as a
            project-root-relative POSIX string. Returned in
            :attr:`PromptsResponse.path`.

    Methods:
        read: Parse :attr:`prompts_path` and return a
            :class:`PromptsResponse`.
    """

    def __init__(
        self,
        prompts_path: Path = DEFAULT_PROMPTS_PATH,
        relative_posix_path: str = DEFAULT_PROMPTS_RELATIVE_POSIX,
    ) -> None:
        """Store the injected prompts path and its relative-POSIX form.

        Args:
            prompts_path (Path): Absolute path to the prompts JSON.
                Defaults to :data:`DEFAULT_PROMPTS_PATH` so the web
                process and the worker container both resolve the
                same bytes on disk.
            relative_posix_path (str): Project-root-relative POSIX
                form of ``prompts_path``. Defaults to
                :data:`DEFAULT_PROMPTS_RELATIVE_POSIX`. When a test
                swaps ``prompts_path`` it should also set this
                argument so the DTO stays self-consistent.
        """
        self.prompts_path = prompts_path
        self.relative_posix_path = relative_posix_path

    def read(self) -> PromptsResponse:
        """Parse the prompts JSON and return a :class:`PromptsResponse`.

        Returns:
            PromptsResponse: The parsed registry. Empty ``prompts``
            dict when the file contains only an empty JSON object.

        Raises:
            FileNotFoundError: If :attr:`prompts_path` does not exist.
            ValueError: If the file is not valid JSON or is not a
                top-level object.
        """
        if not self.prompts_path.is_file():
            raise FileNotFoundError(
                f"Prompts file not found: {self.prompts_path}"
            )
        with self.prompts_path.open("r", encoding="utf-8") as file_handle:
            parsed_document = json.load(file_handle)
        if not isinstance(parsed_document, dict):
            raise ValueError(
                f"Prompts file {self.prompts_path} must be a JSON object; "
                f"got {type(parsed_document).__name__}"
            )
        prompts = {
            str(key): PromptEntry.model_validate(body)
            for key, body in parsed_document.items()
        }
        return PromptsResponse(
            path=self.relative_posix_path,
            prompts=prompts,
        )


__all__ = [
    "DEFAULT_PROMPTS_PATH",
    "DEFAULT_PROMPTS_RELATIVE_POSIX",
    "PromptsRepository",
]
