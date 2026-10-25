from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
)

from app.models.user import Role

# bcrypt only hashes the first 72 bytes of a password.
MAX_PASSWORD_BYTES = 72


def _lower(value: str) -> str:
    return value.strip().lower()


class RegisterRequest(BaseModel):
    # No `role` field: registration always creates a `user`; extra keys are ignored.
    email: Annotated[EmailStr, AfterValidator(_lower)]
    full_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    password: str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes")
        return value


class LoginRequest(BaseModel):
    # No format or length rules: bad credentials are always a 401, never a 422.
    email: Annotated[str, AfterValidator(_lower)]
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: Role
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserOut
