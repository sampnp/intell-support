"""SQLAlchemy models.

Every model module must be imported here so that `Base.metadata` (used by Alembic) sees it.
"""

from app.db import Base
from app.models.document import Document, DocumentChunk, DocumentStatus
from app.models.suggestion import TicketSuggestion
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
    "Document",
    "DocumentChunk",
    "DocumentStatus",
    "EventType",
    "Role",
    "Ticket",
    "TicketCategory",
    "TicketComment",
    "TicketEvent",
    "TicketPriority",
    "TicketStatus",
    "TicketSuggestion",
    "User",
]
