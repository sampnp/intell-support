"""Ticket endpoints: create, list, detail, edit, status, assign, comments, events, suggestions."""

from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_agent
from app.core.permissions import (
    ensure_can_assign,
    ensure_can_comment,
    ensure_can_edit,
    get_visible_ticket,
)
from app.db import get_db
from app.models.ticket import Ticket, TicketCategory, TicketPriority, TicketStatus
from app.models.user import User
from app.schemas.tickets import (
    AssignRequest,
    CommentCreate,
    CommentOut,
    EventOut,
    StatusChange,
    TicketCreate,
    TicketOut,
    TicketPage,
    TicketSummary,
    TicketUpdate,
)
from app.schemas.retrieval import SuggestionsResponse
from app.services import suggestions as suggestion_service
from app.services import tickets as ticket_service
from app.services import workflow
from app.services.embeddings import Embedder, get_embedder
from app.services.vector_store import VectorStore, get_vector_store

router = APIRouter(prefix="/tickets", tags=["tickets"])


def _ticket_out(ticket: Ticket, user: User) -> TicketOut:
    out = TicketOut.model_validate(ticket)
    out.allowed_transitions = workflow.allowed_transitions(user, ticket)
    return out


@router.post("", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
def create_ticket(
    data: TicketCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    embedder: Embedder = Depends(get_embedder),
    store: VectorStore = Depends(get_vector_store),
) -> TicketOut:
    ticket = ticket_service.create_ticket(
        db,
        user,
        data,
        suggest=lambda t: suggestion_service.snapshot_suggestions(db, t, embedder, store),
    )
    return _ticket_out(ticket, user)


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
    return _ticket_out(get_visible_ticket(db, ticket_id, user), user)


@router.patch("/{ticket_id}", response_model=TicketOut)
def update_ticket(
    ticket_id: int,
    data: TicketUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketOut:
    ticket = get_visible_ticket(db, ticket_id, user)
    ensure_can_edit(user, ticket)
    return _ticket_out(ticket_service.update_ticket(db, user, ticket, data), user)


@router.post("/{ticket_id}/status", response_model=TicketOut)
def change_status(
    ticket_id: int,
    data: StatusChange,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketOut:
    ticket = get_visible_ticket(db, ticket_id, user)
    return _ticket_out(workflow.change_status(db, user, ticket, data.status), user)


@router.post("/{ticket_id}/assign", response_model=TicketOut)
def assign_ticket(
    ticket_id: int,
    data: AssignRequest,
    agent: User = Depends(require_agent),
    db: Session = Depends(get_db),
) -> TicketOut:
    ticket = get_visible_ticket(db, ticket_id, agent)
    ensure_can_assign(ticket)
    return _ticket_out(ticket_service.assign_ticket(db, agent, ticket, data.agent_id), agent)


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


@router.get("/{ticket_id}/suggestions", response_model=SuggestionsResponse)
def get_suggestions(
    ticket_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SuggestionsResponse:
    ticket = get_visible_ticket(db, ticket_id, user)
    return SuggestionsResponse.model_validate(suggestion_service.get_suggestions(db, ticket))


@router.post("/{ticket_id}/suggestions/refresh", response_model=SuggestionsResponse)
def refresh_suggestions(
    ticket_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    embedder: Embedder = Depends(get_embedder),
    store: VectorStore = Depends(get_vector_store),
) -> SuggestionsResponse:
    ticket = get_visible_ticket(db, ticket_id, user)
    suggestion_service.snapshot_suggestions(db, ticket, embedder, store)
    return SuggestionsResponse.model_validate(suggestion_service.get_suggestions(db, ticket))
