from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import select

from app.config import get_settings
from app.core.security import verify_password
from app.models.user import User
from tests.conftest import DEFAULT_PASSWORD

REGISTER = "/api/auth/register"
LOGIN = "/api/auth/login"
ME = "/api/auth/me"


def register_payload(**overrides):
    payload = {"email": "new.user@example.com", "full_name": "New User", "password": "s3cret-pass"}
    payload.update(overrides)
    return payload


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def token_for(sub, *, secret=None, expires_in=timedelta(minutes=5)) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {"sub": str(sub), "iat": now, "exp": now + expires_in}
    return jwt.encode(payload, secret or settings.jwt_secret, algorithm=settings.jwt_algorithm)


# --- register ---


def test_register_creates_user_and_logs_in(client, db_session):
    response = client.post(REGISTER, json=register_payload(email="New.User@Example.COM"))

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "new.user@example.com"
    assert body["user"]["full_name"] == "New User"
    assert body["user"]["role"] == "user"
    assert "password" not in response.text
    assert "password_hash" not in body["user"]

    me = client.get(ME, headers=bearer(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["id"] == body["user"]["id"]

    stored = db_session.scalar(select(User).where(User.id == body["user"]["id"]))
    assert stored.password_hash != "s3cret-pass"
    assert verify_password("s3cret-pass", stored.password_hash)


def test_register_ignores_role_in_body(client):
    response = client.post(REGISTER, json=register_payload(role="agent"))

    assert response.status_code == 201
    assert response.json()["user"]["role"] == "user"


def test_register_strips_full_name(client):
    response = client.post(REGISTER, json=register_payload(full_name="  Ada Lovelace  "))

    assert response.status_code == 201
    assert response.json()["user"]["full_name"] == "Ada Lovelace"


def test_register_duplicate_email_is_conflict(client, make_user):
    make_user(email="taken@example.com")

    response = client.post(REGISTER, json=register_payload(email="Taken@Example.com"))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"email": "not-an-email"}, "email"),
        ({"password": "7-chars"}, "password"),
        ({"password": "é" * 37}, "password"),  # 37 chars but 74 bytes: over bcrypt's limit
        ({"full_name": "   "}, "full_name"),
        ({"full_name": "x" * 101}, "full_name"),
    ],
)
def test_register_validation_errors(client, overrides, field):
    response = client.post(REGISTER, json=register_payload(**overrides))

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"][0]["loc"] == ["body", field]


def test_register_accepts_72_byte_password(client):
    response = client.post(REGISTER, json=register_payload(password="a" * 72))

    assert response.status_code == 201


# --- login ---


def test_login_returns_working_token(client, user):
    response = client.post(
        LOGIN, json={"email": user.email.upper(), "password": DEFAULT_PASSWORD}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["id"] == user.id
    assert "password_hash" not in body["user"]

    me = client.get(ME, headers=bearer(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["email"] == user.email


def test_login_wrong_password_and_unknown_email_look_the_same(client, user):
    wrong_password = client.post(LOGIN, json={"email": user.email, "password": "wrong-password"})
    unknown_email = client.post(
        LOGIN, json={"email": "nobody@example.com", "password": DEFAULT_PASSWORD}
    )

    for response in (wrong_password, unknown_email):
        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"
        assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert wrong_password.json() == unknown_email.json()


def test_login_short_password_is_401_not_422(client, user):
    response = client.post(LOGIN, json={"email": user.email, "password": "x"})

    assert response.status_code == 401


# --- me ---


def test_me_returns_current_user(client, agent, auth_headers):
    response = client.get(ME, headers=auth_headers(agent))

    assert response.status_code == 200
    assert response.json() == {
        "id": agent.id,
        "email": agent.email,
        "full_name": agent.full_name,
        "role": "agent",
        "created_at": response.json()["created_at"],
    }


def test_me_without_token_is_401(client):
    response = client.get(ME)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"


@pytest.mark.parametrize(
    "make_header",
    [
        pytest.param(lambda user: {"Authorization": "Basic dXNlcjpwYXNz"}, id="basic-scheme"),
        pytest.param(lambda user: bearer("not-a-jwt"), id="garbage"),
        pytest.param(lambda user: bearer(token_for(user.id, secret="x" * 40)), id="wrong-secret"),
        pytest.param(
            lambda user: bearer(token_for(user.id, expires_in=timedelta(minutes=-1))),
            id="expired",
        ),
        pytest.param(lambda user: bearer(token_for("abc")), id="non-integer-sub"),
    ],
)
def test_me_with_invalid_token_is_401(client, user, make_header):
    response = client.get(ME, headers=make_header(user))

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "INVALID_TOKEN"


def test_me_with_token_for_deleted_user_is_401(client, db_session, make_user, auth_headers):
    gone = make_user()
    headers = auth_headers(gone)
    db_session.delete(gone)
    db_session.flush()

    response = client.get(ME, headers=headers)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"
