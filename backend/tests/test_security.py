from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.config import get_settings
from app.core.errors import UnauthorizedError
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_and_verify_password():
    password_hash = hash_password("s3cret-pass")

    assert password_hash != "s3cret-pass"
    assert verify_password("s3cret-pass", password_hash)
    assert not verify_password("wrong-pass", password_hash)


def test_verify_password_with_malformed_hash_is_false():
    assert not verify_password("s3cret-pass", "not-a-bcrypt-hash")


def test_token_round_trip():
    assert decode_access_token(create_access_token(42)) == 42


def test_tampered_token_is_rejected():
    token = create_access_token(42)
    header, payload, signature = token.split(".")
    tampered = ".".join([header, payload, signature[::-1]])

    with pytest.raises(UnauthorizedError) as excinfo:
        decode_access_token(tampered)
    assert excinfo.value.code == "INVALID_TOKEN"


def test_expired_token_is_rejected():
    settings = get_settings()
    past = datetime.now(UTC) - timedelta(hours=1)
    token = jwt.encode(
        {"sub": "42", "iat": past, "exp": past + timedelta(minutes=5)},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(UnauthorizedError):
        decode_access_token(token)


def test_token_without_sub_is_rejected():
    settings = get_settings()
    now = datetime.now(UTC)
    token = jwt.encode(
        {"iat": now, "exp": now + timedelta(minutes=5)},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(UnauthorizedError):
        decode_access_token(token)
