"""Shared error-response DTOs.

Contents and relationships
--------------------------

- :class:`ValidationErrorItem` — one issue inside a
  :class:`pydantic.ValidationError`, flattened into an HTTP-friendly
  shape.
- :class:`ErrorResponse` — the envelope returned by every non-success
  HTTP response installed by :mod:`server.errors`.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.errors` constructs :class:`ErrorResponse` instances when
  translating exceptions to HTTP responses.
- :mod:`server.schemas.flow` reuses :class:`ValidationErrorItem` inside
  :class:`server.schemas.flow.FlowValidationResponse`.
"""

from __future__ import annotations

from typing import Any, List

from pydantic import BaseModel, ConfigDict, Field


class ValidationErrorItem(BaseModel):
    """One field-level validation issue.

    Attributes:
        loc (List[Any]): The path to the offending field, mirroring the
            shape reported by :class:`pydantic.ValidationError`. For
            example ``["flow", "steps", 0, "type"]``.
        msg (str): Human-readable description of the issue.
        type (str): Machine-readable error type (for example
            ``"value_error"``).
    """

    model_config = ConfigDict(extra="forbid")

    loc: List[Any] = Field(default_factory=list)
    msg: str
    type: str


class ErrorResponse(BaseModel):
    """Envelope wrapping one or more :class:`ValidationErrorItem` entries.

    Attributes:
        errors (List[ValidationErrorItem]): One entry per issue. Most
            responses contain exactly one entry; Pydantic validation
            failures may produce several.
    """

    model_config = ConfigDict(extra="forbid")

    errors: List[ValidationErrorItem] = Field(default_factory=list)
