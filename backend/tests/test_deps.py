import logging

import pytest
from fastapi import APIRouter, Depends

from app.core.deps import require_agent
from app.models.user import User


@pytest.fixture
def app(app):
    """The conftest app plus a route that only agents may call."""
    router = APIRouter(prefix="/test-deps")

    @router.get("/agents-only")
    def agents_only(user: User = Depends(require_agent)):
        return {"user_id": user.id}

    app.include_router(router)
    return app


def test_require_agent_allows_agent(client, agent, auth_headers):
    response = client.get("/test-deps/agents-only", headers=auth_headers(agent))

    assert response.status_code == 200
    assert response.json() == {"user_id": agent.id}


def test_require_agent_rejects_user(client, user, auth_headers, caplog):
    with caplog.at_level(logging.WARNING, logger="app.auth"):
        response = client.get("/test-deps/agents-only", headers=auth_headers(user))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AGENT_REQUIRED"
    assert any(
        "permission_denied" in r.getMessage() and f"user_id={user.id}" in r.getMessage()
        for r in caplog.records
    )


def test_require_agent_without_token_is_401(client):
    response = client.get("/test-deps/agents-only")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"
