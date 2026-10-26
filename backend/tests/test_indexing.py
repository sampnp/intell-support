import logging

from qdrant_client.http import models as qm
from sqlalchemy import func, select

from app.models.document import DocumentChunk
from app.services.vector_store import get_vector_store
from tests.fakes import BrokenStore

DOCUMENTS = "/api/kb/documents"


def chunk_count(db_session, document_id):
    return db_session.scalar(
        select(func.count()).where(DocumentChunk.document_id == document_id)
    )


def reindex(client, auth_headers, as_user, document_id):
    return client.post(f"{DOCUMENTS}/{document_id}/reindex", headers=auth_headers(as_user))


def search_ids(client, auth_headers, user, q, mode):
    body = client.get(
        "/api/kb/search", params={"q": q, "mode": mode}, headers=auth_headers(user)
    ).json()
    return [hit["document_id"] for hit in body["results"]]


def test_upload_indexes_chunks_in_qdrant(
    upload, client, auth_headers, agent, db_session, sample_kb, vector_store, qdrant_client
):
    document = upload(agent, sample_kb / "getting-started-guide.pdf").json()

    detail = client.get(f"{DOCUMENTS}/{document['id']}", headers=auth_headers(agent)).json()
    assert detail["vector_indexed"] is True
    assert vector_store.count_for_document(document["id"]) == detail["chunk_count"]

    same_document = qm.FieldCondition(
        key="document_id", match=qm.MatchValue(value=document["id"])
    )
    points, _ = qdrant_client.scroll(
        vector_store.collection, scroll_filter=qm.Filter(must=[same_document]), limit=100
    )
    chunk_ids = set(
        str(i)
        for i in db_session.scalars(
            select(DocumentChunk.id).where(DocumentChunk.document_id == document["id"])
        )
    )
    assert {str(p.id) for p in points} == chunk_ids
    assert {p.payload["page"] for p in points} == {1, 2, 3}
    assert all(p.payload["document_title"] == "getting-started-guide" for p in points)


def test_vector_failure_keeps_document_ready_and_reindex_recovers(
    app, upload, client, auth_headers, agent, user, sample_kb, vector_store, caplog
):
    app.dependency_overrides[get_vector_store] = lambda: BrokenStore()
    with caplog.at_level(logging.WARNING, logger="app.ingestion"):
        document = upload(agent, sample_kb / "sync-troubleshooting.txt").json()
    assert any("ingestion_vector_index_failed" in r.getMessage() for r in caplog.records)

    detail = client.get(f"{DOCUMENTS}/{document['id']}", headers=auth_headers(agent)).json()
    assert detail["status"] == "ready"
    assert detail["vector_indexed"] is False
    assert document["id"] in search_ids(client, auth_headers, user, "conflicted copy", "keyword")

    app.dependency_overrides[get_vector_store] = lambda: vector_store  # Qdrant is back
    assert document["id"] not in search_ids(
        client, auth_headers, user, "conflicted copy", "semantic"
    )
    response = reindex(client, auth_headers, agent, document["id"])

    assert response.status_code == 200
    assert response.json()["vector_indexed"] is True
    assert document["id"] in search_ids(client, auth_headers, user, "conflicted copy", "semantic")


def test_reindex_is_idempotent(
    upload, client, auth_headers, agent, db_session, sample_kb, vector_store
):
    document_id = upload(agent, sample_kb / "billing-refund-policy.pdf").json()["id"]
    expected = chunk_count(db_session, document_id)

    for _ in range(2):
        assert reindex(client, auth_headers, agent, document_id).status_code == 200
        assert vector_store.count_for_document(document_id) == expected


def test_reindex_with_qdrant_down_is_503(
    app, upload, client, auth_headers, agent, sample_kb
):
    document_id = upload(agent, sample_kb / "billing-refund-policy.pdf").json()["id"]
    app.dependency_overrides[get_vector_store] = lambda: BrokenStore()

    response = reindex(client, auth_headers, agent, document_id)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "VECTOR_INDEX_UNAVAILABLE"
    detail = client.get(f"{DOCUMENTS}/{document_id}", headers=auth_headers(agent)).json()
    assert detail["vector_indexed"] is False


def test_reindex_failed_document_is_409(upload, client, auth_headers, agent, sample_kb):
    document_id = upload(agent, sample_kb / "malformed" / "image-only.pdf").json()["id"]

    response = reindex(client, auth_headers, agent, document_id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DOCUMENT_NOT_READY"


def test_reindex_is_agent_only(upload, client, auth_headers, agent, user, sample_kb):
    document_id = upload(agent, sample_kb / "billing-refund-policy.pdf").json()["id"]

    assert reindex(client, auth_headers, user, document_id).status_code == 403
    assert client.post(f"{DOCUMENTS}/{document_id}/reindex").status_code == 401
    assert reindex(client, auth_headers, agent, 999999).status_code == 404


def test_delete_removes_document_from_both_stores(
    client, auth_headers, agent, user, db_session, indexed_kb, vector_store
):
    document = indexed_kb["sync-troubleshooting"]
    assert vector_store.count_for_document(document.id) > 0

    response = client.delete(f"{DOCUMENTS}/{document.id}", headers=auth_headers(agent))

    assert response.status_code == 204
    assert chunk_count(db_session, document.id) == 0
    assert vector_store.count_for_document(document.id) == 0
    for mode in ("semantic", "keyword"):
        assert document.id not in search_ids(client, auth_headers, user, "conflicted copy", mode)


def test_delete_still_works_when_qdrant_is_down(
    app, client, auth_headers, agent, db_session, indexed_kb, caplog
):
    document = indexed_kb["sync-troubleshooting"]
    app.dependency_overrides[get_vector_store] = lambda: BrokenStore()

    with caplog.at_level(logging.WARNING, logger="app.kb"):
        response = client.delete(f"{DOCUMENTS}/{document.id}", headers=auth_headers(agent))

    assert response.status_code == 204
    assert chunk_count(db_session, document.id) == 0
    assert any("kb_vector_delete_failed" in r.getMessage() for r in caplog.records)


def test_orphan_points_never_surface(
    app, client, auth_headers, agent, user, indexed_kb, vector_store
):
    """Qdrant was down during delete: its points remain, but search joins back to Postgres."""
    document = indexed_kb["sync-troubleshooting"]
    app.dependency_overrides[get_vector_store] = lambda: BrokenStore()
    client.delete(f"{DOCUMENTS}/{document.id}", headers=auth_headers(agent))
    app.dependency_overrides[get_vector_store] = lambda: vector_store

    assert vector_store.count_for_document(document.id) > 0
    found = search_ids(client, auth_headers, user, "conflicted copy", "semantic")
    assert document.id not in found
