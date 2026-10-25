"""Ticket visibility and action checks — the single place these rules live (docs/PLAN.md §7)."""

import logging

from sqlalchemy import Select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.models.ticket import Ticket, TicketStatus
from app.models.user import Role, User

logger = logging.getLogger("app.permissions")


def is_agent(user: User) -> bool:
    return user.role == Role.agent


def can_see_internal(user: User) -> bool:
    """Internal notes and internal events are never returned to users."""
    return is_agent(user)


def can_view_ticket(user: User, ticket: Ticket) -> bool:
    return is_agent(user) or ticket.created_by == user.id


def ticket_scope(stmt: Select, user: User) -> Select:
    """Restrict a ticket query to what the user may see: agents all, users their own."""
    if is_agent(user):
        return stmt
    return stmt.where(Ticket.created_by == user.id)


def _ticket_not_found() -> NotFoundError:
    return NotFoundError("Ticket not found", code="TICKET_NOT_FOUND")


def get_visible_ticket(db: Session, ticket_id: int, user: User) -> Ticket:
    """Load a ticket the user may see. Someone else's ticket is a 404, not a 403, so ticket ids
    can't be enumerated."""
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise _ticket_not_found()
    if not can_view_ticket(user, ticket):
        logger.warning(
            "permission_denied user_id=%s ticket_id=%s reason=not_owner", user.id, ticket.id
        )
        raise _ticket_not_found()
    return ticket


def ensure_can_edit(user: User, ticket: Ticket) -> None:
    """Title/description: the owner only, while the ticket is open."""
    if is_agent(user):
        logger.warning(
            "permission_denied user_id=%s ticket_id=%s reason=agent_cannot_edit",
            user.id,
            ticket.id,
        )
        raise ForbiddenError("Agents cannot edit tickets", code="TICKET_EDIT_FORBIDDEN")
    if ticket.status != TicketStatus.open:
        raise ConflictError(
            "Only open tickets can be edited",
            code="TICKET_NOT_EDITABLE",
            details={"status": ticket.status},
        )


def ensure_can_comment(user: User, ticket: Ticket, is_internal: bool) -> None:
    if is_internal and not is_agent(user):
        logger.warning(
            "permission_denied user_id=%s ticket_id=%s reason=internal_note",
            user.id,
            ticket.id,
        )
        raise ForbiddenError(
            "Only agents can post internal notes", code="INTERNAL_NOTE_FORBIDDEN"
        )
    if ticket.status == TicketStatus.closed:
        raise ConflictError("Closed tickets cannot take comments", code="TICKET_CLOSED")
