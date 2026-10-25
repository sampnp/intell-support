"""SQLAlchemy models.

Every model module must be imported here so that `Base.metadata` (used by Alembic) sees it.
"""

from app.db import Base

__all__ = ["Base"]
