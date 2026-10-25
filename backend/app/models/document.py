import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.ticket import in_values
from app.models.user import User


class DocumentStatus(StrEnum):
    processing = "processing"
    ready = "ready"
    failed = "failed"


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(in_values("status", DocumentStatus), name="status_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(20), default=DocumentStatus.processing, server_default=DocumentStatus.processing
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    # False until the chunks are embedded into Qdrant (WP6); keyword search works regardless.
    vector_indexed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    uploader: Mapped[User] = relationship()


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_document_index"),
        Index("ix_document_chunks_tsv", "tsv", postgresql_using="gin"),
    )

    # Shared with the Qdrant point id (docs/PLAN.md §4).
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    # Null for TXT documents (one logical "page").
    page_number: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', text)", persisted=True), deferred=True
    )
