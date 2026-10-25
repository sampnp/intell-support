"""Password hashing (bcrypt) and JWT access tokens (PyJWT)."""

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.config import get_settings
from app.core.errors import UnauthorizedError

# bcrypt work factor. Tests lower it to keep the suite fast.
BCRYPT_ROUNDS = 12


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        # Malformed hash, or a password over bcrypt's 72-byte limit.
        return False


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int:
    """Return the user id in a valid token; raise UnauthorizedError otherwise."""
    settings = get_settings()
    invalid = UnauthorizedError("Invalid or expired token", code="INVALID_TOKEN")
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "iat", "sub"]},
        )
        return int(payload["sub"])
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise invalid from exc
