"""Postgres full-text search over document chunks — the fallback when semantic search is down
(docs/PLAN.md §9).

All query words must match first (`websearch_to_tsquery`, as specified). If that finds nothing,
any word may match, ranked so passages sharing more words come first: long ticket text
(title + description) rarely has every word in one passage, and the fallback must still help.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import Text, cast, func, literal_column, select
from sqlalchemy.dialects.postgresql import TSQUERY
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentChunk, DocumentStatus

TS_CONFIG = literal_column("'english'::regconfig")


@dataclass(frozen=True)
class SearchHit:
    chunk_id: uuid.UUID
    document_id: int
    document_title: str
    page: int | None
    snippet: str
    score: float


def _run(db: Session, tsquery, k: int) -> list[SearchHit]:
    # Normalization 32 maps the rank into 0..1 (rank / (rank + 1)).
    score = func.ts_rank_cd(DocumentChunk.tsv, tsquery, 32).label("score")
    rows = db.execute(
        select(
            DocumentChunk.id,
            DocumentChunk.document_id,
            Document.title,
            DocumentChunk.page_number,
            DocumentChunk.text,
            score,
        )
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            Document.status == DocumentStatus.ready,
            DocumentChunk.tsv.op("@@")(tsquery),
        )
        .order_by(score.desc(), DocumentChunk.document_id, DocumentChunk.chunk_index)
        .limit(k)
    ).all()
    return [
        SearchHit(
            chunk_id=row.id,
            document_id=row.document_id,
            document_title=row.title,
            page=row.page_number,
            snippet=row.text,
            score=round(float(row.score), 4),
        )
        for row in rows
    ]


def keyword_search(db: Session, q: str, k: int) -> list[SearchHit]:
    hits = _run(db, func.websearch_to_tsquery(TS_CONFIG, q), k)
    if hits:
        return hits
    # 'conflict' & 'copi'  ->  'conflict' | 'copi'
    any_word = cast(
        func.replace(cast(func.plainto_tsquery(TS_CONFIG, q), Text), "&", "|"), TSQUERY
    )
    return _run(db, any_word, k)
