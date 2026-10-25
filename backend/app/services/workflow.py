"""Ticket state machine (docs/PLAN.md §6). The transition table below is the single definition."""

import logging
from typing import Literal

from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.models.ticket import EventType, Ticket, TicketStatus
from app.models.user import Role, User
from app.services.events import add_event, utcnow

logger = logging.getLogger("app.workflow")

Actor = Literal["agent", "owner"]

AGENT: frozenset[Actor] = frozenset({"agent"})
OWNER: frozenset[Actor] = frozenset({"owner"})
OWNER_OR_AGENT: frozenset[Actor] = frozenset({"owner", "agent"})

# from status -> {to status -> who may make that move}. Order is the order shown to clients.
TRANSITIONS: dict[TicketStatus, dict[TicketStatus, frozenset[Actor]]] = {
    TicketStatus.open: {
        TicketStatus.in_progress: AGENT,
        TicketStatus.resolved: AGENT,
    },
    TicketStatus.in_progress: {
        TicketStatus.waiting_for_user: AGENT,
        TicketStatus.resolved: AGENT,
    },
    TicketStatus.waiting_for_user: {
        # Also happens automatically when the owner comments (apply_owner_comment).
        TicketStatus.in_progress: AGENT,
        TicketStatus.resolved: AGENT,
    },
    TicketStatus.resolved: {
        TicketStatus.closed: OWNER_OR_AGENT,
        TicketStatus.open: OWNER,  # reopen
    },
    TicketStatus.closed: {},  # terminal
}


def actor_kinds(user: User, ticket: Ticket) -> set[Actor]:
    """An agent who opened the ticket is both."""
    kinds: set[Actor] = set()
    if user.role == Role.agent:
        kinds.add("agent")
    if ticket.created_by == user.id:
        kinds.add("owner")
    return kinds


def allowed_transitions(user: User, ticket: Ticket) -> list[TicketStatus]:
    kinds = actor_kinds(user, ticket)
    moves = TRANSITIONS[TicketStatus(ticket.status)]
    return [to for to, actors in moves.items() if kinds & actors]


def _set_status(db: Session, actor: User, ticket: Ticket, to: TicketStatus, **extra) -> None:
    from_status = ticket.status
    ticket.status = to
    ticket.updated_at = utcnow()
    add_event(
        db, ticket, actor, EventType.status_changed, {"from": from_status, "to": to, **extra}
    )
    logger.info(
        "status_changed ticket_id=%s from=%s to=%s actor_id=%s automatic=%s",
        ticket.id,
        from_status,
        to,
        actor.id,
        bool(extra.get("automatic")),
    )


def change_status(db: Session, user: User, ticket: Ticket, to: TicketStatus) -> Ticket:
    allowed = allowed_transitions(user, ticket)
    if to not in allowed:
        raise ConflictError(
            "Invalid status transition",
            code="INVALID_TRANSITION",
            details={"from": ticket.status, "to": to, "allowed": allowed},
        )
    _set_status(db, user, ticket, to)
    db.commit()
    return ticket


def apply_owner_comment(db: Session, user: User, ticket: Ticket) -> None:
    """The owner replying to a ticket that waits on them moves it back to in_progress.

    Does not commit: the caller commits it together with the comment."""
    if ticket.created_by == user.id and ticket.status == TicketStatus.waiting_for_user:
        _set_status(db, user, ticket, TicketStatus.in_progress, automatic=True)
