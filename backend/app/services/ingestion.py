"""KB ingestion (docs/PLAN.md §9): validate -> extract -> chunk -> store -> (index, WP6).

Uploads are validated synchronously; extraction, chunking and storage run in a background task
with their own database session. Processing never raises: a document always ends `ready` or
`failed` with a readable `error_message`.
"""

import logging
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath

from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.core.errors import BadRequestError, PayloadTooLargeError, UnsupportedMediaTypeError
from app.db import SessionLocal
from app.models.document import Document, DocumentChunk, DocumentStatus
from app.models.user import User
from app.services.chunking import chunk_pages

logger = logging.getLogger("app.ingestion")

# extension -> (kind, content type stored on the document)
ALLOWED_TYPES = {".pdf": ("pdf", "application/pdf"), ".txt": ("txt", "text/plain")}

NO_TEXT_MESSAGE = "No extractable text (scanned or image-only PDF?)"
CORRUPT_PDF_MESSAGE = "Could not read the PDF (the file may be corrupt)"
ENCRYPTED_PDF_MESSAGE = "Encrypted PDFs are not supported"
UNEXPECTED_MESSAGE = "Unexpected error while processing the file"

Pages = list[tuple[int | None, str]]
SessionFactory = Callable[[], AbstractContextManager[Session]]


class ExtractionError(Exception):
    """A file passed validation but its text can't be used; the message is shown to agents."""


@dataclass(frozen=True)
class ValidatedUpload:
    kind: str
    content_type: str


def validate_upload(filename: str, data: bytes, max_bytes: int) -> ValidatedUpload:
    extension = PurePath(filename or "").suffix.lower()
    if extension not in ALLOWED_TYPES:
        raise UnsupportedMediaTypeError(
            "Only .pdf and .txt files are supported",
            code="UNSUPPORTED_FILE_TYPE",
            details={"filename": filename},
        )
    if len(data) > max_bytes:
        raise PayloadTooLargeError(
            f"File is larger than the {max_bytes // (1024 * 1024)} MB limit",
            code="FILE_TOO_LARGE",
            details={"max_bytes": max_bytes},
        )
    if not data:
        raise BadRequestError("The file is empty", code="EMPTY_FILE")

    kind, content_type = ALLOWED_TYPES[extension]
    if kind == "pdf" and not data.startswith(b"%PDF"):
        raise BadRequestError("Not a PDF file (missing %PDF header)", code="INVALID_FILE")
    if kind == "txt":
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise BadRequestError("Text files must be UTF-8 encoded", code="INVALID_FILE")
        if not text.strip():
            raise BadRequestError("The file is empty", code="EMPTY_FILE")
    return ValidatedUpload(kind, content_type)


def extract_pages(kind: str, data: bytes) -> Pages:
    """TXT is one page with no number; PDFs keep their page numbers (1-based)."""
    if kind == "txt":
        return [(None, data.decode("utf-8-sig"))]

    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            raise ExtractionError(ENCRYPTED_PDF_MESSAGE)
        pages: Pages = [
            (number, page.extract_text() or "")
            for number, page in enumerate(reader.pages, start=1)
        ]
    except ExtractionError:
        raise
    except Exception as exc:  # pypdf raises many error types on malformed input
        raise ExtractionError(CORRUPT_PDF_MESSAGE) from exc

    if not pages:
        raise ExtractionError(CORRUPT_PDF_MESSAGE)
    if not any(text.strip() for _, text in pages):
        raise ExtractionError(NO_TEXT_MESSAGE)
    return pages


def default_title(filename: str) -> str:
    return (PurePath(filename).stem.strip() or filename)[:200]


def create_document(
    db: Session,
    user: User,
    *,
    filename: str,
    content_type: str,
    size_bytes: int,
    title: str | None = None,
) -> Document:
    document = Document(
        title=title or default_title(filename),
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        status=DocumentStatus.processing,
        uploaded_by=user.id,
    )
    db.add(document)
    db.commit()
    return document


def _mark_failed(db: Session, document: Document, message: str) -> None:
    document.status = DocumentStatus.failed
    document.error_message = message
    document.chunk_count = 0
    document.vector_indexed = False
    db.commit()


def process_document(db: Session, document: Document, data: bytes, kind: str) -> Document:
    """Extract, chunk and store. Never raises; the outcome is on the document."""
    started = time.perf_counter()
    pages_count = 0
    error: str | None = None
    try:
        pages = extract_pages(kind, data)
        pages_count = len(pages)
        chunks = chunk_pages(pages)
        if not chunks:
            raise ExtractionError(NO_TEXT_MESSAGE)
        db.add_all(
            DocumentChunk(
                document_id=document.id,
                chunk_index=chunk.chunk_index,
                page_number=chunk.page_number,
                text=chunk.text,
            )
            for chunk in chunks
        )
        # WP6: embed + upsert into Qdrant here; on failure keep vector_indexed = False.
        document.status = DocumentStatus.ready
        document.chunk_count = len(chunks)
        document.vector_indexed = False
        document.error_message = None
        db.commit()
    except ExtractionError as exc:
        db.rollback()
        error = str(exc)
        _mark_failed(db, document, error)
    except Exception:
        logger.exception("ingestion_unexpected_error document_id=%s", document.id)
        db.rollback()
        error = UNEXPECTED_MESSAGE
        _mark_failed(db, document, error)

    duration_ms = (time.perf_counter() - started) * 1000
    if error is None:
        logger.info(
            "ingestion document_id=%s status=ready pages=%s chunks=%s duration_ms=%.1f",
            document.id,
            pages_count,
            document.chunk_count,
            duration_ms,
        )
    else:
        logger.warning(
            "ingestion document_id=%s status=failed pages=%s chunks=0 duration_ms=%.1f error=%r",
            document.id,
            pages_count,
            duration_ms,
            error,
        )
    return document


def ingest_bytes(
    db: Session,
    user: User,
    filename: str,
    data: bytes,
    *,
    max_bytes: int,
    title: str | None = None,
) -> Document:
    """Validate, create and process synchronously (tests, seed script)."""
    upload = validate_upload(filename, data, max_bytes)
    document = create_document(
        db,
        user,
        filename=filename,
        content_type=upload.content_type,
        size_bytes=len(data),
        title=title,
    )
    return process_document(db, document, data, upload.kind)


@contextmanager
def _new_session() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session_factory() -> SessionFactory:
    """Dependency: sessions for background work, independent of the request's session."""
    return _new_session


def process_in_background(
    session_factory: SessionFactory, document_id: int, data: bytes, kind: str
) -> None:
    with session_factory() as db:
        document = db.get(Document, document_id)
        if document is None:
            logger.warning("ingestion_skipped document_id=%s reason=deleted", document_id)
            return
        process_document(db, document, data, kind)
