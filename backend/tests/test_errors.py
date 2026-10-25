import pytest
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationFailedError


class Item(BaseModel):
    name: str
    quantity: int


@pytest.fixture
def app(app):
    """The conftest app plus routes that raise each kind of error."""
    router = APIRouter(prefix="/test-errors")

    @router.get("/not-found")
    def not_found():
        raise NotFoundError()

    @router.get("/ticket-not-found")
    def ticket_not_found():
        raise NotFoundError("Ticket not found", code="TICKET_NOT_FOUND")

    @router.get("/forbidden")
    def forbidden():
        raise ForbiddenError()

    @router.get("/conflict")
    def conflict():
        raise ConflictError("Invalid transition", details={"allowed": ["resolved"]})

    @router.get("/validation-failed")
    def validation_failed():
        raise ValidationFailedError()

    @router.post("/items")
    def create_item(item: Item):
        return item

    @router.get("/unauthorized")
    def unauthorized():
        raise HTTPException(401, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})

    @router.get("/crash")
    def crash():
        raise RuntimeError("secret internal detail")

    app.include_router(router)
    return app


@pytest.mark.parametrize(
    ("path", "status", "code", "message"),
    [
        ("/test-errors/not-found", 404, "NOT_FOUND", "Not found"),
        ("/test-errors/forbidden", 403, "FORBIDDEN", "Forbidden"),
        ("/test-errors/validation-failed", 422, "VALIDATION_FAILED", "Validation failed"),
    ],
)
def test_app_errors_use_envelope(client, path, status, code, message):
    response = client.get(path)

    assert response.status_code == status
    assert response.json() == {"error": {"code": code, "message": message, "details": None}}


def test_app_error_code_and_message_override(client):
    response = client.get("/test-errors/ticket-not-found")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "TICKET_NOT_FOUND", "message": "Ticket not found", "details": None}
    }


def test_app_error_details(client):
    response = client.get("/test-errors/conflict")

    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "CONFLICT",
        "message": "Invalid transition",
        "details": {"allowed": ["resolved"]},
    }


def test_request_validation_error(client):
    response = client.post("/test-errors/items", json={"name": "x", "quantity": "many"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["message"] == "Request validation failed"
    assert error["details"][0]["loc"] == ["body", "quantity"]
    assert error["details"][0]["type"] == "int_parsing"


def test_unknown_route_is_not_found_envelope(client):
    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "NOT_FOUND", "message": "Not Found", "details": None}}


def test_method_not_allowed_envelope(client):
    response = client.delete("/api/health")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_http_exception_keeps_headers(client):
    response = client.get("/test-errors/unauthorized")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json() == {
        "error": {"code": "UNAUTHORIZED", "message": "Not authenticated", "details": None}
    }


def test_unexpected_error_does_not_leak(client):
    response = client.get("/test-errors/crash")

    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "INTERNAL_ERROR"
    assert error["message"] == "Internal server error"
    assert "secret" not in response.text
    assert "Traceback" not in response.text
