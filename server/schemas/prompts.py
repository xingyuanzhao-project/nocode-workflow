"""HTTP DTOs for the prompts-registry endpoint.

``GET /api/prompts`` returns every key from ``config/prompts.json`` so
the GUI's ``PromptTab`` can render:

- The list of available ``prompts_ref`` keys users may pick from.
- The base instructions and ``output_format`` stored under each key,
  used as the starting point when a user adds ``prompt_overrides`` on
  a step.

Contents and relationships
--------------------------

- :class:`PromptEntry` — one key's body (instructions + output format).
- :class:`PromptsResponse` — response of ``GET /api/prompts``.

How the rest of the system uses this module
-------------------------------------------

- :class:`server.services.prompts_repository.PromptsRepository` returns
  :class:`PromptsResponse` from :meth:`PromptsRepository.read`.
- The GUI's ``PromptTab`` consumes the DTO to populate its prompt-key
  dropdown and its placeholder reference sidebar.

Invariants enforced by this module
----------------------------------

- :class:`PromptEntry` allows unknown fields (``extra="allow"``) so the
  schema never rejects a prompts.json entry that grows new optional
  keys in the future. Only the two documented fields (``instructions``
  and ``output_format``) are typed.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PromptEntry(BaseModel):
    """One entry in ``config/prompts.json``, keyed by ``prompts_ref``.

    Attributes:
        instructions (List[str]): Ordered list of instruction lines.
            Passed verbatim to the LLM as the system prompt template;
            placeholders like ``{input_text_label}`` are substituted
            at call time by :mod:`src.prompt_resolver`.
        output_format (Optional[Dict[str, Any]]): Example JSON shape
            the model should emit. ``None`` for prompts that do not
            define an ``output_format`` (for example the
            ``classification`` key's output shape lives in
            :attr:`src.flow_loader.ProcessorConfig.io_schema` instead).
    """

    model_config = ConfigDict(extra="allow")

    instructions: List[str] = Field(default_factory=list)
    output_format: Optional[Dict[str, Any]] = None


class PromptsResponse(BaseModel):
    """Response of ``GET /api/prompts``.

    Attributes:
        path (str): Project-root-relative POSIX path of the prompts
            file on disk (for example ``"config/prompts.json"``).
            The GUI uses this to populate the ``prompts_ref`` reference
            form ``"<path>::<key>"`` users may paste into the Prompt
            tab's override editor.
        prompts (Dict[str, PromptEntry]): Every key in the prompts
            file, mapped to its entry. Keys match the values users
            write under :attr:`src.flow_loader.ProcessorConfig.prompts_ref`
            (bare-key form).
    """

    model_config = ConfigDict(extra="forbid")

    path: str
    prompts: Dict[str, PromptEntry] = Field(default_factory=dict)
