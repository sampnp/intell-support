"""Ticket endpoints: create, list, detail, edit, comments, events."""

from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.permissions import ensure_can_comment, ensure_can_edit, get_visible_ticket
from app.db import get_db
from app.models.ticket import TicketCategory, TicketPriority, TicketStatus
from app.models.user import User
from app.schemas.tickets import (
    CommentCreate,
    CommentOut,
    EventOut,
    TicketCreate,
    TicketOut,
    TicketPage,
    TicketSummary,
    TicketUpdate,
)
from app.services import tickets as ticket_service

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post("", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
def create_ticket(
    data: TicketCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketOut:
    return TicketOut.model_validate(ticket_service.create_ticket(db, user, data))


@router.get("", response_model=TicketPage)
def list_tickets(
    q: str | None = Query(None, max_length=200),
    status: TicketStatus | None = None,
    priority: TicketPriority | None = None,
    category: TicketCategory | None = None,
    assigned: Literal["me", "unassigned"] | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketPage:
    filters = ticket_service.TicketFilters(
        q=q,
        status=status,
        priority=priority,
        category=category,
        assigned=assigned,
        page=page,
        page_size=page_size,
    )
    items, total = ticket_service.list_tickets(db, user, filters)
    return TicketPage(
        items=[TicketSummary.model_validate(ticket) for ticket in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{ticket_id}", response_model=TicketOut)
def get_ticket(
    ticket_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketOut:
    return TicketOut.model_validate(get_visible_ticket(db, ticket_id, user))


@router.patch("/{ticket_id}", response_model=TicketOut)
def update_ticket(
    ticket_id: int,
    data: TicketUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketOut:
    ticket = get_visible_ticket(db, ticket_id, user)
    ensure_can_edit(user, ticket)
    return TicketOut.model_validate(ticket_service.update_ticket(db, user, ticket, data))


@router.get("/{ticket_id}/comments", response_model=list[CommentOut])
def list_comments(
    ticket_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CommentOut]:
    ticket = get_visible_ticket(db, ticket_id, user)
    return [CommentOut.model_validate(c) for c in ticket_service.list_comments(db, user, ticket)]


@router.post(
    "/{ticket_id}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED
)
def add_comment(
    ticket_id: int,
    data: CommentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CommentOut:
    ticket = get_visible_ticket(db, ticket_id, user)
    ensure_can_comment(user, ticket, data.is_internal)
    return CommentOut.model_validate(ticket_service.add_comment(db, user, ticket, data))


@router.get("/{ticket_id}/events", response_model=list[EventOut])
def list_events(
    ticket_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[EventOut]:
    ticket = get_visible_ticket(db, ticket_id, user)
    return [EventOut.model_validate(e) for e in ticket_service.list_events(db, user, ticket)]
