"""Ticket suggestions snapshot (docs/PLAN.md §9): retrieval runs on ticket creation and on
refresh; the result is stored so the ticket page shows the same passages until refreshed."""

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentChunk
from app.models.suggestion import TicketSuggestion
from app.models.ticket import Ticket
from app.services import retrieval
from app.services.embeddings import Embedder
from app.services.events import utcnow
from app.services.keyword_search import SearchHit
from app.services.vector_store import VectorStore

logger = logging.getLogger("app.suggestions")

SUGGESTION_COUNT = 3


@dataclass(frozen=True)
class Suggestions:
    mode: str | None
    insufficient: bool
    updated_at: datetime | None
    results: list[SearchHit]


def _replace_rows(db: Session, ticket: Ticket, result: retrieval.SearchResult | None) -> None:
    db.execute(delete(TicketSuggestion).where(TicketSuggestion.ticket_id == ticket.id))
    if result is not None:
        db.add_all(
            TicketSuggestion(
                ticket_id=ticket.id,
                chunk_id=hit.chunk_id,
                rank=rank,
                score=hit.score,
                retrieval_mode=result.mode,
            )
            for rank, hit in enumerate(result.results, start=1)
        )
    ticket.suggestions_mode = result.mode if result is not None else None
    ticket.suggestions_updated_at = utcnow()


def snapshot_suggestions(
    db: Session, ticket: Ticket, embedder: Embedder, store: VectorStore
) -> None:
    """Replace the ticket's snapshot. Never raises: on failure the snapshot is left empty with
    mode null, so retrieval problems can never fail ticket creation."""
    query = f"{ticket.title}\n{ticket.description}"
    try:
        result = retrieval.search(db, embedder, store, query, SUGGESTION_COUNT, mode="auto")
        _replace_rows(db, ticket, result)
        db.commit()
        logger.info(
            "suggestions_snapshot ticket_id=%s mode=%s results=%s",
            ticket.id,
            result.mode,
            len(result.results),
        )
    except Exception:
        logger.exception("suggestions_failed ticket_id=%s", ticket.id)
        db.rollback()
        try:
            _replace_rows(db, ticket, None)
            db.commit()
        except Exception:
            logger.exception("suggestions_clear_failed ticket_id=%s", ticket.id)
            db.rollback()


def get_suggestions(db: Session, ticket: Ticket) -> Suggestions:
    rows = db.execute(
        select(
            TicketSuggestion.score,
            DocumentChunk.id,
            DocumentChunk.document_id,
            Document.title,
            DocumentChunk.page_number,
            DocumentChunk.text,
        )
        .join(DocumentChunk, DocumentChunk.id == TicketSuggestion.chunk_id)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(TicketSuggestion.ticket_id == ticket.id)
        .order_by(TicketSuggestion.rank)
    ).all()
    hits = [
        SearchHit(
            chunk_id=row.id,
            document_id=row.document_id,
            document_title=row.title,
            page=row.page_number,
            snippet=row.text,
            score=row.score,
        )
        for row in rows
    ]
    return Suggestions(
        mode=ticket.suggestions_mode,
        insufficient=not hits,
        updated_at=ticket.suggestions_updated_at,
        results=hits,
    )
