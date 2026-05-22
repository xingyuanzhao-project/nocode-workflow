"""HTTP exception translation for the FastAPI app.

Wraps the most common domain exceptions raised by services into
well-typed HTTP responses via a single entry point,
:func:`install_exception_handlers`. Every handler returns an
:class:`server.schemas.errors.ErrorResponse` body so clients see a
consistent shape across routes.

Contents and relationships
--------------------------

- :func:`install_exception_handlers` — idempotent installer called
  once from :func:`server.app.create_app`.
- Private handlers for the four exception types handled here:
  :class:`FileNotFoundError` → 404, :class:`ValueError` → 400,
  :class:`PermissionError` → 403, and
  :class:`pydantic.ValidationError` → 422.

How the rest of the system uses this module
-------------------------------------------

- Services raise plain Python exceptions (``FileNotFoundError``,
  ``ValueError``). The routes stay oblivious; the handlers installed
  here translate the exception into a typed HTTP response at the edge.

Invariants enforced by this module
----------------------------------

- Every handler returns a :class:`fastapi.responses.JSONResponse`
  whose body validates as :class:`server.schemas.errors.ErrorResponse`.
- The installer never shadows user-registered handlers; FastAPI's
  :meth:`FastAPI.exception_handler` replaces prior handlers for the
  same exception type, so callers that install additional handlers
  should do so after calling :func:`install_exception_handlers`.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from server.schemas.errors import ErrorResponse, ValidationErrorItem


def _not_found_handler(_request: Request, exc: FileNotFoundError) -> JSONResponse:
    """Translate :class:`FileNotFoundError` into a 404 response.

    Args:
        _request (Request): Unused; required by FastAPI's handler
            signature.
        exc (FileNotFoundError): The raised exception.

    Returns:
        JSONResponse: 404 response with an :class:`ErrorResponse` body.
    """
    envelope = ErrorResponse(
        errors=[ValidationErrorItem(loc=[], msg=str(exc), type="not_found")]
    )
    return JSONResponse(status_code=404, content=envelope.model_dump())


def _bad_request_handler(_request: Request, exc: ValueError) -> JSONResponse:
    """Translate :class:`ValueError` into a 400 response.

    Args:
        _request (Request): Unused.
        exc (ValueError): The raised exception.

    Returns:
        JSONResponse: 400 response with an :class:`ErrorResponse` body.
    """
    envelope = ErrorResponse(
        errors=[ValidationErrorItem(loc=[], msg=str(exc), type="value_error")]
    )
    return JSONResponse(status_code=400, content=envelope.model_dump())


def _forbidden_handler(
    _request: Request, exc: PermissionError
) -> JSONResponse:
    """Translate :class:`PermissionError` into a 403 response.

    Args:
        _request (Request): Unused.
        exc (PermissionError): The raised exception.

    Returns:
        JSONResponse: 403 response with an :class:`ErrorResponse` body.
    """
    envelope = ErrorResponse(
        errors=[ValidationErrorItem(loc=[], msg=str(exc), type="forbidden")]
    )
    return JSONResponse(status_code=403, content=envelope.model_dump())


def _validation_error_handler(
    _request: Request, exc: ValidationError
) -> JSONResponse:
    """Translate :class:`pydantic.ValidationError` into a 422 response.

    Args:
        _request (Request): Unused.
        exc (ValidationError): The raised exception.

    Returns:
        JSONResponse: 422 response with an :class:`ErrorResponse` body.
    """
    envelope = ErrorResponse(
        errors=[
            ValidationErrorItem(
                loc=list(issue.get("loc", ())),
                msg=str(issue.get("msg", "")),
                type=str(issue.get("type", "")),
            )
            for issue in exc.errors()
        ]
    )
    return JSONResponse(status_code=422, content=envelope.model_dump())


def install_exception_handlers(app: FastAPI) -> None:
    """Register the package's exception handlers on ``app``.

    Args:
        app (FastAPI): The application to configure.

    Returns:
        None.
    """
    app.add_exception_handler(FileNotFoundError, _not_found_handler)
    app.add_exception_handler(ValueError, _bad_request_handler)
    app.add_exception_handler(PermissionError, _forbidden_handler)
    app.add_exception_handler(ValidationError, _validation_error_handler)
