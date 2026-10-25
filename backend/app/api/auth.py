"""Auth endpoints: register, login, me."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.security import create_access_token
from app.db import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id), user=UserOut.model_validate(user)
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    # Registering logs the user in: same response body as /login.
    return _token_response(auth_service.register_user(db, data))


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return _token_response(auth_service.authenticate(db, data.email, data.password))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
