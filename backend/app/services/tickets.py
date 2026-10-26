"""Ticket, comment and event logic. Every change and its ticket_events row share one commit."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ConflictError, ValidationFailedError
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
from app.models.user import Role, User
from app.schemas.tickets import CommentCreate, TicketCreate, TicketUpdate
from app.services.events import add_event, utcnow
from app.services.workflow import apply_owner_comment

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


def create_ticket(
    db: Session,
    user: User,
    data: TicketCreate,
    suggest: Callable[[Ticket], None] | None = None,
) -> Ticket:
    """Create the ticket and its `created` event, then (optionally) take the suggestions
    snapshot. `suggest` runs after the commit and never raises, so it can't fail creation."""
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
    add_event(db, ticket, user, EventType.created)
    db.commit()
    logger.info("ticket_created ticket_id=%s user_id=%s", ticket.id, user.id)
    if suggest is not None:
        suggest(ticket)
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
    ticket.updated_at = utcnow()
    add_event(db, ticket, user, EventType.ticket_updated, {"fields": changed})
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
    add_event(db, ticket, user, event_type, {"comment_id": comment.id})
    ticket.updated_at = utcnow()
    if not data.is_internal:
        # Owner reply on a waiting_for_user ticket moves it back to in_progress (same commit).
        apply_owner_comment(db, user, ticket)
    db.commit()
    logger.info(
        "comment_added ticket_id=%s comment_id=%s internal=%s",
        ticket.id,
        comment.id,
        data.is_internal,
    )
    return comment


def assign_ticket(db: Session, agent: User, ticket: Ticket, agent_id: int | None) -> Ticket:
    """Assign, reassign or (agent_id=None) unassign. The caller has checked agent role/status."""
    if agent_id is not None:
        assignee = db.get(User, agent_id)
        if assignee is None or assignee.role != Role.agent:
            raise ValidationFailedError(
                "Assignee must be an existing agent",
                code="ASSIGNEE_NOT_AGENT",
                details={"agent_id": agent_id},
            )
    if agent_id == ticket.assigned_to:
        raise ConflictError(
            "Ticket already has that assignment",
            code="ASSIGNMENT_UNCHANGED",
            details={"agent_id": agent_id},
        )

    from_agent_id = ticket.assigned_to
    ticket.assigned_to = agent_id
    ticket.updated_at = utcnow()
    add_event(
        db,
        ticket,
        agent,
        EventType.assigned,
        {"from_agent_id": from_agent_id, "to_agent_id": agent_id},
    )
    db.commit()
    db.refresh(ticket, ["assignee"])
    logger.info(
        "ticket_assigned ticket_id=%s from_agent_id=%s to_agent_id=%s actor_id=%s",
        ticket.id,
        from_agent_id,
        agent_id,
        agent.id,
    )
    return ticket


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
