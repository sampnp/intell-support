"""SQLAlchemy models.

Every model module must be imported here so that `Base.metadata` (used by Alembic) sees it.
"""

from app.db import Base
from app.models.ticket import (
    EventType,
    Ticket,
    TicketCategory,
    TicketComment,
    TicketEvent,
    TicketPriority,
    TicketStatus,
)
from app.models.user import Role, User

__all__ = [
    "Base",
    "EventType",
    "Role",
    "Ticket",
    "TicketCategory",
    "TicketComment",
    "TicketEvent",
    "TicketPriority",
    "TicketStatus",
    "User",
]
