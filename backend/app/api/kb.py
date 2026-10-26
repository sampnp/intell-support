"""Knowledge base endpoints: search (any signed-in user) and document management (agents only:
upload, list, detail, delete, reindex)."""

import logging
from pathlib import PurePath
from typing import Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.core.deps import get_current_user, require_agent
from app.core.errors import NotFoundError, ValidationFailedError
from app.db import get_db
from app.models.document import Document
from app.models.user import User
from app.schemas.kb import DocumentOut
from app.schemas.retrieval import SearchResponse
from app.services import retrieval
from app.services.embeddings import Embedder, get_embedder
from app.services.ingestion import (
    SessionFactory,
    create_document,
    get_session_factory,
    process_in_background,
    reindex_document,
    validate_upload,
)
from app.services.vector_store import VectorStore, get_vector_store

logger = logging.getLogger("app.kb")

router = APIRouter(prefix="/kb", tags=["kb"])


def _get_document(db: Session, document_id: int) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise NotFoundError("Document not found", code="DOCUMENT_NOT_FOUND")
    return document


@router.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=1, max_length=500),
    k: int = Query(3, ge=1, le=10),
    mode: Literal["auto", "semantic", "keyword"] = "auto",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    embedder: Embedder = Depends(get_embedder),
    store: VectorStore = Depends(get_vector_store),
) -> SearchResponse:
    query = q.strip()
    if not query:
        raise ValidationFailedError(
            "Search query must not be blank",
            code="VALIDATION_ERROR",
            details=[{"loc": ["query", "q"], "msg": "must not be blank", "type": "blank"}],
        )
    result = retrieval.search(db, embedder, store, query, k, mode=mode)
    return SearchResponse.model_validate(result)


@router.post("/documents", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED)
def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str | None = Form(None, max_length=200),
    agent: User = Depends(require_agent),
    db: Session = Depends(get_db),
    session_factory: SessionFactory = Depends(get_session_factory),
    embedder: Embedder = Depends(get_embedder),
    store: VectorStore = Depends(get_vector_store),
) -> DocumentOut:
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    # One byte over the limit is enough to know it's too large.
    data = file.file.read(max_bytes + 1)
    filename = PurePath(file.filename or "").name
    upload = validate_upload(filename, data, max_bytes)

    document = create_document(
        db,
        agent,
        filename=filename,
        content_type=upload.content_type,
        size_bytes=len(data),
        title=(title or "").strip() or None,
    )
    logger.info(
        "kb_upload_accepted document_id=%s kind=%s size_bytes=%s user_id=%s",
        document.id,
        upload.kind,
        len(data),
        agent.id,
    )
    background_tasks.add_task(
        process_in_background, session_factory, document.id, data, upload.kind, embedder, store
    )
    return DocumentOut.model_validate(document)


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(
    agent: User = Depends(require_agent),
    db: Session = Depends(get_db),
) -> list[DocumentOut]:
    documents = db.scalars(
        select(Document)
        .options(selectinload(Document.uploader))
        .order_by(Document.created_at.desc(), Document.id.desc())
    )
    return [DocumentOut.model_validate(document) for document in documents]


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: int,
    agent: User = Depends(require_agent),
    db: Session = Depends(get_db),
) -> DocumentOut:
    return DocumentOut.model_validate(_get_document(db, document_id))


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    agent: User = Depends(require_agent),
    db: Session = Depends(get_db),
    store: VectorStore = Depends(get_vector_store),
) -> Response:
    document = _get_document(db, document_id)
    try:
        store.delete_document(document_id)
    except Exception as exc:
        # Best effort: search joins hits back to Postgres, so orphaned points never surface.
        logger.warning("kb_vector_delete_failed document_id=%s error=%r", document_id, exc)
    # Chunks (and the ticket suggestions pointing at them) go by ON DELETE CASCADE.
    db.delete(document)
    db.commit()
    logger.info("kb_document_deleted document_id=%s user_id=%s", document_id, agent.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/documents/{document_id}/reindex", response_model=DocumentOut)
def reindex(
    document_id: int,
    agent: User = Depends(require_agent),
    db: Session = Depends(get_db),
    embedder: Embedder = Depends(get_embedder),
    store: VectorStore = Depends(get_vector_store),
) -> DocumentOut:
    document = reindex_document(db, _get_document(db, document_id), embedder, store)
    return DocumentOut.model_validate(document)
