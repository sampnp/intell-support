"""Registration and login rules."""

import logging
from functools import cache

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, UnauthorizedError
from app.core.security import hash_password, verify_password
from app.models.user import Role, User
from app.schemas.auth import RegisterRequest

logger = logging.getLogger("app.auth")


def _email_taken() -> ConflictError:
    return ConflictError("Email already registered", code="EMAIL_ALREADY_REGISTERED")


@cache
def _dummy_hash() -> str:
    # Checked for unknown emails so login takes as long as for a real account.
    return hash_password("dummy-password-for-timing")


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def register_user(db: Session, data: RegisterRequest) -> User:
    if get_user_by_email(db, data.email) is not None:
        raise _email_taken()

    # Registration always creates a `user`; agents come from the seed script.
    user = User(
        email=data.email,
        full_name=data.full_name,
        password_hash=hash_password(data.password),
        role=Role.user,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        # A concurrent registration took the email between the check and the insert.
        db.rollback()
        raise _email_taken() from exc
    db.refresh(user)
    logger.info("auth_register user_id=%s", user.id)
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = get_user_by_email(db, email)
    if user is None:
        verify_password(password, _dummy_hash())
        valid = False
    else:
        valid = verify_password(password, user.password_hash)

    if not valid:
        logger.info("auth_login outcome=failed")
        raise UnauthorizedError("Invalid email or password", code="INVALID_CREDENTIALS")

    logger.info("auth_login outcome=ok user_id=%s", user.id)
    return user
