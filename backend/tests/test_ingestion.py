import logging

import pytest
from sqlalchemy import func, select, text

from app.config import get_settings
from app.models.document import Document, DocumentChunk
from app.services import ingestion
from app.services.chunking import OVERLAP_CHARS, TARGET_CHARS
from app.services.ingestion import (
    CORRUPT_PDF_MESSAGE,
    NO_TEXT_MESSAGE,
    UNEXPECTED_MESSAGE,
    ingest_bytes,
)

DOCUMENTS = "/api/kb/documents"

# filename, number of PDF pages (None for TXT), a word that occurs in the document
SAMPLE_DOCS = [
    ("getting-started-guide.pdf", 3, "verification"),
    ("billing-refund-policy.pdf", 2, "refund"),
    ("sharing-permissions-faq.pdf", 2, "expiry"),
    ("account-login-troubleshooting.txt", None, "authenticator"),
    ("sync-troubleshooting.txt", None, "conflicted"),
    ("security-data-privacy.txt", None, "encrypted"),
]


def chunks_of(db_session, document_id):
    stmt = (
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
    )
    return list(db_session.scalars(stmt))


def document_count(db_session):
    return db_session.scalar(select(func.count()).select_from(Document))


def detail(client, auth_headers, agent, document_id):
    return client.get(f"{DOCUMENTS}/{document_id}", headers=auth_headers(agent))


# --- the sample knowledge base ---


@pytest.mark.parametrize(("filename", "pages", "word"), SAMPLE_DOCS)
def test_sample_document_ingests(
    upload, client, auth_headers, agent, db_session, sample_kb, filename, pages, word
):
    response = upload(agent, sample_kb / filename)

    assert response.status_code == 202
    accepted = response.json()
    assert accepted["status"] == "processing"  # the response is sent before processing runs
    assert accepted["filename"] == filename
    assert accepted["uploaded_by"]["id"] == agent.id

    document = detail(client, auth_headers, agent, accepted["id"]).json()
    assert document["status"] == "ready"
    assert document["error_message"] is None
    assert document["vector_indexed"] is False

    chunks = chunks_of(db_session, accepted["id"])
    assert document["chunk_count"] == len(chunks) > 0
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert all(0 < len(c.text) <= TARGET_CHARS + OVERLAP_CHARS + 1 for c in chunks)
    page_numbers = [c.page_number for c in chunks]
    if pages is None:
        assert set(page_numbers) == {None}
    else:
        assert set(page_numbers) == set(range(1, pages + 1))
        assert page_numbers == sorted(page_numbers)

    matches = db_session.scalar(
        text(
            "SELECT count(*) FROM document_chunks WHERE document_id = :id "
            "AND tsv @@ websearch_to_tsquery('english', :q)"
        ),
        {"id": accepted["id"], "q": word},
    )
    assert matches >= 1


def test_content_types_and_default_title(upload, agent, sample_kb):
    pdf = upload(agent, sample_kb / "billing-refund-policy.pdf").json()
    txt = upload(agent, sample_kb / "sync-troubleshooting.txt").json()

    assert (pdf["title"], pdf["content_type"]) == ("billing-refund-policy", "application/pdf")
    assert (txt["title"], txt["content_type"]) == ("sync-troubleshooting", "text/plain")
    assert pdf["size_bytes"] == (sample_kb / "billing-refund-policy.pdf").stat().st_size


def test_ingest_bytes_processes_synchronously(db_session, agent, sample_kb):
    path = sample_kb / "security-data-privacy.txt"

    document = ingest_bytes(
        db_session, agent, path.name, path.read_bytes(), max_bytes=10 * 1024 * 1024
    )

    assert document.status == "ready"
    assert document.chunk_count == len(chunks_of(db_session, document.id)) > 0


# --- malformed files ---


@pytest.mark.parametrize(
    ("filename", "code"),
    [
        ("empty.txt", "EMPTY_FILE"),
        ("binary-garbage.txt", "INVALID_FILE"),
        ("not-really.pdf", "INVALID_FILE"),
    ],
)
def test_invalid_files_are_rejected_immediately(
    upload, agent, db_session, sample_kb, filename, code
):
    response = upload(agent, sample_kb / "malformed" / filename)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == code
    assert document_count(db_session) == 0


@pytest.mark.parametrize(
    ("filename", "message"),
    [
        ("corrupt.pdf", CORRUPT_PDF_MESSAGE),
        ("image-only.pdf", NO_TEXT_MESSAGE),
    ],
)
def test_unreadable_pdfs_end_failed(
    upload, client, auth_headers, agent, db_session, sample_kb, filename, message
):
    response = upload(agent, sample_kb / "malformed" / filename)

    assert response.status_code == 202
    document = detail(client, auth_headers, agent, response.json()["id"]).json()
    assert document["status"] == "failed"
    assert document["error_message"] == message
    assert document["chunk_count"] == 0
    assert chunks_of(db_session, document["id"]) == []


def test_image_only_message_matches_spec():
    assert NO_TEXT_MESSAGE == "No extractable text (scanned or image-only PDF?)"


@pytest.mark.parametrize("filename", ["notes.docx", "README", "photo.png"])
def test_unsupported_extension_is_415(upload, agent, db_session, filename):
    response = upload(agent, (filename, b"some bytes"))

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"
    assert document_count(db_session) == 0


def test_size_limit(upload, agent, db_session, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)
    limit = 1024 * 1024

    too_big = upload(agent, ("big.txt", b"a" * (limit + 1)))
    just_fits = upload(agent, ("fits.txt", b"a" * limit))

    assert too_big.status_code == 413
    assert too_big.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert just_fits.status_code == 202
    assert document_count(db_session) == 1


def test_whitespace_only_txt_is_empty(upload, agent):
    response = upload(agent, ("blank.txt", b"  \n\n\t  \n"))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "EMPTY_FILE"


def test_extension_is_case_insensitive_and_bom_is_stripped(
    upload, client, auth_headers, agent, db_session
):
    response = upload(agent, ("NOTES.TXT", "﻿Hello from a BOM file.".encode("utf-8")))

    assert response.status_code == 202
    document = detail(client, auth_headers, agent, response.json()["id"]).json()
    assert document["status"] == "ready"
    assert chunks_of(db_session, document["id"])[0].text == "Hello from a BOM file."


def test_missing_file_field_is_422(client, agent, auth_headers):
    response = client.post(DOCUMENTS, headers=auth_headers(agent))

    assert response.status_code == 422


def test_unexpected_processing_error_marks_failed(
    upload, client, auth_headers, agent, monkeypatch, caplog
):
    def explode(pages):
        raise RuntimeError("boom")

    monkeypatch.setattr(ingestion, "chunk_pages", explode)

    with caplog.at_level(logging.INFO, logger="app.ingestion"):
        response = upload(agent, ("notes.txt", b"Some perfectly good text."))

    document = detail(client, auth_headers, agent, response.json()["id"]).json()
    assert document["status"] == "failed"
    assert document["error_message"] == UNEXPECTED_MESSAGE
    assert "boom" not in document["error_message"]
    assert any("ingestion_unexpected_error" in r.getMessage() for r in caplog.records)


def test_ingestion_is_logged(upload, agent, caplog):
    with caplog.at_level(logging.INFO, logger="app.ingestion"):
        response = upload(agent, ("notes.txt", b"Some perfectly good text."))

    document_id = response.json()["id"]
    assert any(
        f"ingestion document_id={document_id} status=ready" in r.getMessage()
        for r in caplog.records
    )


# --- titles, duplicates, list, detail, delete ---


def test_custom_title_is_stripped(upload, agent, sample_kb):
    response = upload(agent, sample_kb / "billing-refund-policy.pdf", title="  Billing FAQ  ")

    assert response.json()["title"] == "Billing FAQ"


def test_title_too_long_is_422(upload, agent, sample_kb):
    response = upload(agent, sample_kb / "billing-refund-policy.pdf", title="x" * 201)

    assert response.status_code == 422


def test_same_file_twice_makes_two_documents(upload, agent, db_session, sample_kb):
    first = upload(agent, sample_kb / "sync-troubleshooting.txt").json()
    second = upload(agent, sample_kb / "sync-troubleshooting.txt").json()

    assert first["id"] != second["id"]
    assert document_count(db_session) == 2


def test_list_is_newest_first(upload, client, auth_headers, agent):
    first = upload(agent, ("a.txt", b"First document text.")).json()
    second = upload(agent, ("b.txt", b"Second document text.")).json()

    listed = client.get(DOCUMENTS, headers=auth_headers(agent)).json()

    assert [d["id"] for d in listed] == [second["id"], first["id"]]
    assert listed[0]["status"] == "ready"


def test_unknown_document_is_404(client, auth_headers, agent):
    response = detail(client, auth_headers, agent, 999999)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


def test_delete_removes_document_and_chunks(
    upload, client, auth_headers, agent, db_session, sample_kb
):
    document_id = upload(agent, sample_kb / "getting-started-guide.pdf").json()["id"]
    assert chunks_of(db_session, document_id)

    response = client.delete(f"{DOCUMENTS}/{document_id}", headers=auth_headers(agent))

    assert response.status_code == 204
    assert chunks_of(db_session, document_id) == []
    assert detail(client, auth_headers, agent, document_id).status_code == 404
    again = client.delete(f"{DOCUMENTS}/{document_id}", headers=auth_headers(agent))
    assert again.status_code == 404


# --- permissions ---


@pytest.fixture
def existing_document(upload, agent):
    return upload(agent, ("existing.txt", b"Existing document text.")).json()


def requests_for(document_id):
    return [
        ("POST", DOCUMENTS, {"files": {"file": ("x.txt", b"Some text.")}}),
        ("GET", DOCUMENTS, {}),
        ("GET", f"{DOCUMENTS}/{document_id}", {}),
        ("DELETE", f"{DOCUMENTS}/{document_id}", {}),
    ]


def test_users_cannot_use_kb_document_endpoints(
    client, auth_headers, user, db_session, existing_document
):
    for method, url, kwargs in requests_for(existing_document["id"]):
        response = client.request(method, url, headers=auth_headers(user), **kwargs)
        assert response.status_code == 403, (method, url)
        assert response.json()["error"]["code"] == "AGENT_REQUIRED"
    assert document_count(db_session) == 1


def test_kb_document_endpoints_require_token(client, existing_document):
    for method, url, kwargs in requests_for(existing_document["id"]):
        response = client.request(method, url, **kwargs)
        assert response.status_code == 401, (method, url)
