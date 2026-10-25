from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Role(StrEnum):
    user = "user"
    agent = "agent"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint("role IN ('user', 'agent')", name="role_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Always stored lowercased (enforced by the check constraint above).
    email: Mapped[str] = mapped_column(String(254), unique=True)
    full_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(60))
    # Plain string + CHECK rather than a native enum, so later migrations stay simple.
    role: Mapped[str] = mapped_column(String(20), default=Role.user, server_default=Role.user)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
