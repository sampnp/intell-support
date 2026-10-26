"""Semantic-first retrieval with keyword fallback and a score threshold (docs/PLAN.md §9).

- mode=auto: semantic (embed query -> Qdrant); on any embedder/Qdrant error, log and use keyword.
- mode=semantic: semantic only; if it can't run -> 503 SEMANTIC_UNAVAILABLE.
- mode=keyword: Postgres full-text search only.
Semantic hits below the threshold are dropped; `insufficient` is true when nothing is left.
The response always states the mode actually used.
"""

import logging
import time
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import ServiceUnavailableError
from app.models.document import Document, DocumentChunk, DocumentStatus
from app.services.embeddings import Embedder
from app.services.keyword_search import SearchHit, keyword_search
from app.services.vector_store import VectorStore

logger = logging.getLogger("app.retrieval")

RequestedMode = Literal["auto", "semantic", "keyword"]
UsedMode = Literal["semantic", "keyword"]

__all__ = ["SearchHit", "SearchResult", "search", "semantic_search"]


@dataclass(frozen=True)
class SearchResult:
    mode: UsedMode
    insufficient: bool
    results: list[SearchHit]


def semantic_search(
    db: Session,
    embedder: Embedder,
    store: VectorStore,
    q: str,
    k: int,
    threshold: float,
) -> list[SearchHit]:
    vector = embedder.embed_query(q)
    # Ask for extra points: some may belong to documents deleted from Postgres.
    scored = store.search(vector, limit=k * 2)
    if not scored:
        return []

    rows = db.execute(
        select(
            DocumentChunk.id,
            DocumentChunk.document_id,
            Document.title,
            DocumentChunk.page_number,
            DocumentChunk.text,
        )
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            DocumentChunk.id.in_([chunk_id for chunk_id, _ in scored]),
            Document.status == DocumentStatus.ready,
        )
    ).all()
    by_id = {row.id: row for row in rows}

    hits: list[SearchHit] = []
    for chunk_id, score in scored:  # Qdrant order: best first
        row = by_id.get(chunk_id)
        if row is None or score < threshold:
            continue
        hits.append(
            SearchHit(
                chunk_id=row.id,
                document_id=row.document_id,
                document_title=row.title,
                page=row.page_number,
                snippet=row.text,
                score=round(float(score), 4),
            )
        )
        if len(hits) == k:
            break
    return hits


def search(
    db: Session,
    embedder: Embedder,
    store: VectorStore,
    q: str,
    k: int,
    mode: RequestedMode = "auto",
    threshold: float | None = None,
) -> SearchResult:
    if threshold is None:
        threshold = get_settings().retrieval_score_threshold
    started = time.perf_counter()
    fallback = False

    if mode == "keyword":
        used: UsedMode = "keyword"
        hits = keyword_search(db, q, k)
    else:
        try:
            hits = semantic_search(db, embedder, store, q, k, threshold)
            used = "semantic"
        except Exception as exc:
            if mode == "semantic":
                logger.warning("retrieval_semantic_unavailable error=%r", exc)
                raise ServiceUnavailableError(
                    "Semantic search is unavailable", code="SEMANTIC_UNAVAILABLE"
                ) from exc
            logger.warning("retrieval_fallback reason=%r", exc)
            fallback = True
            used = "keyword"
            hits = keyword_search(db, q, k)

    result = SearchResult(mode=used, insufficient=not hits, results=hits)
    logger.info(
        "retrieval mode=%s requested=%s fallback=%s k=%s results=%s top_score=%s latency_ms=%.1f",
        used,
        mode,
        fallback,
        k,
        len(hits),
        hits[0].score if hits else None,
        (time.perf_counter() - started) * 1000,
    )
    return result
