import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class TicketSuggestion(Base):
    """One row of a ticket's suggestions snapshot (docs/PLAN.md §5, §9)."""

    __tablename__ = "ticket_suggestions"
    __table_args__ = (
        UniqueConstraint("ticket_id", "rank", name="uq_ticket_suggestions_ticket_rank"),
        CheckConstraint(
            "retrieval_mode IN ('semantic', 'keyword')", name="retrieval_mode_valid"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), index=True
    )
    # Deleting a KB document removes its chunks and, with them, these rows.
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"), index=True
    )
    rank: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    retrieval_mode: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
