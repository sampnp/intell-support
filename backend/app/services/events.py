"""Writing ticket_events rows. Callers add the event in the same transaction as the change."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.ticket import EventType, Ticket, TicketEvent
from app.models.user import User


def utcnow() -> datetime:
    return datetime.now(UTC)


def add_event(
    db: Session,
    ticket: Ticket,
    actor: User,
    event_type: EventType,
    data: dict[str, Any] | None = None,
) -> TicketEvent:
    event = TicketEvent(
        ticket_id=ticket.id, actor_id=actor.id, event_type=event_type, data=data or {}
    )
    db.add(event)
    return event
