"""Ticket, comment and event logic. Every change and its ticket_events row share one commit."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session, selectinload

from app.core.permissions import can_see_internal, ticket_scope
from app.models.ticket import (
    INTERNAL_EVENT_TYPES,
    EventType,
    Ticket,
    TicketCategory,
    TicketComment,
    TicketEvent,
    TicketPriority,
    TicketStatus,
)
from app.models.user import User
from app.schemas.tickets import CommentCreate, TicketCreate, TicketUpdate

logger = logging.getLogger("app.tickets")

TS_CONFIG = literal_column("'english'::regconfig")


@dataclass
class TicketFilters:
    q: str | None = None
    status: TicketStatus | None = None
    priority: TicketPriority | None = None
    category: TicketCategory | None = None
    assigned: Literal["me", "unassigned"] | None = None
    page: int = 1
    page_size: int = 20


def _now() -> datetime:
    return datetime.now(UTC)


def _add_event(
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


def create_ticket(db: Session, user: User, data: TicketCreate) -> Ticket:
    ticket = Ticket(
        title=data.title,
        description=data.description,
        category=data.category,
        priority=data.priority,
        status=TicketStatus.open,
        created_by=user.id,
    )
    db.add(ticket)
    db.flush()
    _add_event(db, ticket, user, EventType.created)
    # WP6: suggestions snapshot (must never fail ticket creation).
    db.commit()
    logger.info("ticket_created ticket_id=%s user_id=%s", ticket.id, user.id)
    return ticket


def list_tickets(db: Session, user: User, filters: TicketFilters) -> tuple[list[Ticket], int]:
    stmt = ticket_scope(select(Ticket), user)
    if filters.status:
        stmt = stmt.where(Ticket.status == filters.status)
    if filters.priority:
        stmt = stmt.where(Ticket.priority == filters.priority)
    if filters.category:
        stmt = stmt.where(Ticket.category == filters.category)
    if filters.assigned == "me":
        stmt = stmt.where(Ticket.assigned_to == user.id)
    elif filters.assigned == "unassigned":
        stmt = stmt.where(Ticket.assigned_to.is_(None))

    order_by = [Ticket.updated_at.desc(), Ticket.id.desc()]
    q = (filters.q or "").strip()
    if q:
        tsquery = func.websearch_to_tsquery(TS_CONFIG, q)
        stmt = stmt.where(Ticket.search_vector.op("@@")(tsquery))
        order_by.insert(0, func.ts_rank_cd(Ticket.search_vector, tsquery).desc())

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(
        stmt.options(selectinload(Ticket.creator), selectinload(Ticket.assignee))
        .order_by(*order_by)
        .offset((filters.page - 1) * filters.page_size)
        .limit(filters.page_size)
    ).all()
    return list(items), total


def update_ticket(db: Session, user: User, ticket: Ticket, data: TicketUpdate) -> Ticket:
    requested = data.model_dump(exclude_unset=True)
    changed = [field for field, value in requested.items() if getattr(ticket, field) != value]
    if not changed:
        return ticket

    for field in changed:
        setattr(ticket, field, requested[field])
    ticket.updated_at = _now()
    _add_event(db, ticket, user, EventType.ticket_updated, {"fields": changed})
    db.commit()
    logger.info("ticket_updated ticket_id=%s fields=%s", ticket.id, ",".join(changed))
    return ticket


def add_comment(db: Session, user: User, ticket: Ticket, data: CommentCreate) -> TicketComment:
    comment = TicketComment(
        ticket_id=ticket.id, author_id=user.id, body=data.body, is_internal=data.is_internal
    )
    db.add(comment)
    db.flush()
    event_type = EventType.internal_note_added if data.is_internal else EventType.comment_added
    _add_event(db, ticket, user, event_type, {"comment_id": comment.id})
    ticket.updated_at = _now()
    # WP4: owner comment on a waiting_for_user ticket moves it back to in_progress.
    db.commit()
    logger.info(
        "comment_added ticket_id=%s comment_id=%s internal=%s",
        ticket.id,
        comment.id,
        data.is_internal,
    )
    return comment


def list_comments(db: Session, user: User, ticket: Ticket) -> list[TicketComment]:
    stmt = (
        select(TicketComment)
        .where(TicketComment.ticket_id == ticket.id)
        .options(selectinload(TicketComment.author))
        .order_by(TicketComment.created_at, TicketComment.id)
    )
    if not can_see_internal(user):
        stmt = stmt.where(TicketComment.is_internal.is_(False))
    return list(db.scalars(stmt).all())


def list_events(db: Session, user: User, ticket: Ticket) -> list[TicketEvent]:
    stmt = (
        select(TicketEvent)
        .where(TicketEvent.ticket_id == ticket.id)
        .options(selectinload(TicketEvent.actor))
        .order_by(TicketEvent.created_at, TicketEvent.id)
    )
    if not can_see_internal(user):
        stmt = stmt.where(TicketEvent.event_type.not_in(INTERNAL_EVENT_TYPES))
    return list(db.scalars(stmt).all())
