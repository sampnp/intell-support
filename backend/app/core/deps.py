"""Auth dependencies: `get_current_user` and `require_agent`."""

import logging

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token
from app.db import get_db
from app.models.user import Role, User

logger = logging.getLogger("app.auth")

# auto_error=False: FastAPI's default answers a missing token with 403; we want 401.
bearer = HTTPBearer(auto_error=False)


def _invalid_token() -> UnauthorizedError:
    return UnauthorizedError("Invalid or expired token", code="INVALID_TOKEN")


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        # HTTPBearer also returns None for a non-Bearer scheme such as Basic.
        if request.headers.get("Authorization"):
            raise _invalid_token()
        raise UnauthorizedError("Not authenticated", code="NOT_AUTHENTICATED")

    user_id = decode_access_token(credentials.credentials)
    user = db.get(User, user_id)
    if user is None:
        raise _invalid_token()
    return user


def require_agent(request: Request, user: User = Depends(get_current_user)) -> User:
    if user.role != Role.agent:
        logger.warning(
            "permission_denied user_id=%s reason=agent_required path=%s",
            user.id,
            request.url.path,
        )
        raise ForbiddenError("Agent role required", code="AGENT_REQUIRED")
    return user
