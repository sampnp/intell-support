"""AppError hierarchy and the global handlers that turn every error into one envelope:

    {"error": {"code": "TICKET_NOT_FOUND", "message": "Ticket not found", "details": null}}
"""

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import REQUEST_ID_HEADER, request_id_var

logger = logging.getLogger("app.errors")


class AppError(Exception):
    status_code: int = 500
    code: str = "APP_ERROR"
    message: str = "Application error"
    # Extra response headers, e.g. WWW-Authenticate on 401s.
    headers: dict[str, str] | None = None

    def __init__(
        self, message: str | None = None, *, code: str | None = None, details: Any = None
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details = details
        super().__init__(self.message)


class UnauthorizedError(AppError):
    status_code = 401
    code = "UNAUTHORIZED"
    message = "Not authenticated"
    headers = {"WWW-Authenticate": "Bearer"}


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"
    message = "Not found"


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"
    message = "Forbidden"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"
    message = "Conflict"


class ValidationFailedError(AppError):
    status_code = 422
    code = "VALIDATION_FAILED"
    message = "Validation failed"


HTTP_STATUS_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
}


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "details": jsonable_encoder(details)}}
    return JSONResponse(status_code=status_code, content=body, headers=headers)


async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    logger.info("app_error code=%s status=%s path=%s", exc.code, exc.status_code, request.url.path)
    return error_response(exc.status_code, exc.code, exc.message, exc.details, headers=exc.headers)


async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {"loc": list(err.get("loc", ())), "msg": err.get("msg"), "type": err.get("type")}
        for err in exc.errors()
    ]
    return error_response(422, "VALIDATION_ERROR", "Request validation failed", details)


async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = HTTP_STATUS_CODES.get(exc.status_code, "HTTP_ERROR")
    if isinstance(exc.detail, str):
        message, details = exc.detail, None
    else:
        message, details = HTTPStatus(exc.status_code).phrase, exc.detail
    return error_response(exc.status_code, code, message, details, headers=exc.headers)


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # Runs outside RequestIdMiddleware, so restore the id for this log line and the response.
    request_id = getattr(request.state, "request_id", None) or "-"
    token = request_id_var.set(request_id)
    try:
        logger.exception(
            "unhandled_error method=%s path=%s", request.method, request.url.path
        )
    finally:
        request_id_var.reset(token)
    return error_response(
        500,
        "INTERNAL_ERROR",
        "Internal server error",
        {"request_id": request_id},
        headers={REQUEST_ID_HEADER: request_id},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(Exception, handle_unexpected_error)
