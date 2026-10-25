"""Structured, single-line logging and the request-id middleware.

Every log record carries a `request_id` attribute: the id of the HTTP request being handled,
or "-" outside a request. Messages are written as `key=value` pairs.
"""

import logging
import re
import time
import uuid
from contextvars import ContextVar

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s"

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")
_HANDLER_NAME = "intell-support"

logger = logging.getLogger("app.request")


def _install_record_factory() -> None:
    """Attach the current request id to every record, whichever handler ends up emitting it."""
    base_factory = logging.getLogRecordFactory()
    if getattr(base_factory, "_adds_request_id", False):
        return

    def factory(*args, **kwargs) -> logging.LogRecord:
        record = base_factory(*args, **kwargs)
        record.request_id = request_id_var.get()
        return record

    factory._adds_request_id = True  # type: ignore[attr-defined]
    logging.setLogRecordFactory(factory)


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger once; safe to call again (e.g. per test app)."""
    _install_record_factory()
    root = logging.getLogger()
    root.setLevel(level.upper())
    if not any(h.get_name() == _HANDLER_NAME for h in root.handlers):
        handler = logging.StreamHandler()
        handler.set_name(_HANDLER_NAME)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root.addHandler(handler)
    # The Qdrant client logs every HTTP call at INFO via httpx.
    logging.getLogger("httpx").setLevel(logging.WARNING)


class RequestIdMiddleware:
    """Assigns a request id, exposes it to logs and the response, and logs one line per request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get(REQUEST_ID_HEADER)
        request_id = (
            incoming if incoming and _VALID_REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex
        )
        # Shared with request.state, so exception handlers outside this middleware can read it.
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            logger.info(
                "method=%s path=%s status=%s duration_ms=%.1f",
                scope["method"],
                scope["path"],
                status_code,
                (time.perf_counter() - start) * 1000,
            )
            request_id_var.reset(token)
