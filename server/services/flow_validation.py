"""Service that validates raw flow dicts against the flow schema.

The flow schema lives in :mod:`src.flow_loader` as
:class:`src.flow_loader.FlowSchema`. This service wraps it so HTTP
callers can submit a raw :class:`dict` and receive a flattened list of
issues instead of a :class:`pydantic.ValidationError` stack trace.

Contents and relationships
--------------------------

- :class:`FlowValidator` — the service; one method,
  :meth:`FlowValidator.validate`, returns a
  :class:`server.schemas.flow.FlowValidationResponse`.
- :func:`_flatten_validation_error` — helper that converts a
  :class:`pydantic.ValidationError` into a list of
  :class:`server.schemas.errors.ValidationErrorItem`.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.routes.schema` calls :meth:`FlowValidator.validate` from
  the ``POST /api/schema/validate`` handler.
- :mod:`server.services.flow_repository` calls it before writing a flow
  YAML to disk so invalid flows never land in
  :attr:`server.storage.paths.ServerPaths.workflows_dir`.

Invariants enforced by this module
----------------------------------

- The raw flow dict is wrapped in a ``{"flow": ...}`` envelope before
  being passed to :meth:`FlowSchema.model_validate`, matching the
  on-disk YAML's top-level key.
- Validation exceptions from :mod:`src.flow_loader` never bubble out of
  this service unchanged; the caller always sees a
  :class:`FlowValidationResponse`.
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import ValidationError

from src.flow_loader import FlowDocument, FlowSchema, compile_flow_document_to_runtime

from server.schemas.errors import ValidationErrorItem
from server.schemas.flow import FlowValidationResponse


def _flatten_validation_error(
    validation_error: ValidationError,
) -> List[ValidationErrorItem]:
    """Convert one :class:`pydantic.ValidationError` into DTO items.

    Args:
        validation_error (ValidationError): The exception raised by
            :meth:`pydantic.BaseModel.model_validate`.

    Returns:
        List[ValidationErrorItem]: One item per reported issue.
    """
    return [
        ValidationErrorItem(
            loc=list(issue.get("loc", ())),
            msg=str(issue.get("msg", "")),
            type=str(issue.get("type", "")),
        )
        for issue in validation_error.errors()
    ]


class FlowValidator:
    """Service wrapping :class:`src.flow_loader.FlowSchema`.

    Methods:
        validate: Validate a raw flow dict and return a
            :class:`FlowValidationResponse`.
    """

    def validate(self, flow_definition: Dict[str, Any]) -> FlowValidationResponse:
        """Validate ``flow_definition`` against :class:`FlowSchema`.

        Args:
            flow_definition (Dict[str, Any]): Raw flow body as it
                appears under the ``flow:`` key of a flow YAML.

        Returns:
            FlowValidationResponse: ``valid=True`` and empty errors when
            validation succeeds; ``valid=False`` and a flattened error
            list when it fails.
        """
        try:
            document = FlowDocument.model_validate(flow_definition)
        except ValidationError as exc:
            return FlowValidationResponse(
                valid=False,
                errors=_flatten_validation_error(exc),
            )
        try:
            compile_flow_document_to_runtime(document)
        except (ValueError, ValidationError) as exc:
            if isinstance(exc, ValidationError):
                return FlowValidationResponse(
                    valid=False,
                    errors=_flatten_validation_error(exc),
                )
            return FlowValidationResponse(
                valid=False,
                errors=[
                    ValidationErrorItem(
                        loc=["flow"],
                        msg=str(exc),
                        type="value_error",
                    )
                ],
            )
        return FlowValidationResponse(valid=True, errors=[])
