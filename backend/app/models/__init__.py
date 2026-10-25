"""SQLAlchemy models.

Every model module must be imported here so that `Base.metadata` (used by Alembic) sees it.
"""

from app.db import Base
from app.models.user import Role, User

__all__ = ["Base", "Role", "User"]
