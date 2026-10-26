import logging

from sqlalchemy import select

from app.models.suggestion import TicketSuggestion
from app.services import retrieval
from app.services.ingestion import ingest_bytes
from app.services.vector_store import get_vector_store
from tests.fakes import BrokenStore

TICKETS = "/api/tickets"

DOUBLE_CHARGE = {
    "title": "Charged twice this month",
    "description": "I was billed two times for the same period. Duplicate charges refunded?",
    "category": "billing",
}


def create_ticket(client, auth_headers, owner, payload=DOUBLE_CHARGE):
    response = client.post(TICKETS, json=payload, headers=auth_headers(owner))
    assert response.status_code == 201
    return response.json()


def suggestions(client, auth_headers, as_user, ticket_id):
    return client.get(f"{TICKETS}/{ticket_id}/suggestions", headers=auth_headers(as_user))


def rows(db_session, ticket_id):
    stmt = (
        select(TicketSuggestion)
        .where(TicketSuggestion.ticket_id == ticket_id)
        .order_by(TicketSuggestion.rank)
    )
    return list(db_session.scalars(stmt))


def test_ticket_creation_takes_a_snapshot(
    client, auth_headers, user, agent, db_session, indexed_kb
):
    ticket = create_ticket(client, auth_headers, user)

    stored = rows(db_session, ticket["id"])
    assert 1 <= len(stored) <= 3
    assert [r.rank for r in stored] == list(range(1, len(stored) + 1))
    assert {r.retrieval_mode for r in stored} == {"semantic"}

    for reader in (user, agent):
        body = suggestions(client, auth_headers, reader, ticket["id"]).json()
        assert body["mode"] == "semantic"
        assert body["insufficient"] is False
        assert body["updated_at"] is not None
        assert [hit["chunk_id"] for hit in body["results"]] == [str(r.chunk_id) for r in stored]
        assert indexed_kb["billing-refund-policy"].id in [
            hit["document_id"] for hit in body["results"]
        ]
        assert all(hit["document_title"] and hit["snippet"] for hit in body["results"])


def test_ticket_creation_survives_retrieval_failure(
    client, auth_headers, user, indexed_kb, monkeypatch, caplog
):
    def explode(*args, **kwargs):
        raise RuntimeError("retrieval is completely down")

    monkeypatch.setattr(retrieval, "search", explode)

    with caplog.at_level(logging.WARNING, logger="app.suggestions"):
        ticket = create_ticket(client, auth_headers, user)

    body = suggestions(client, auth_headers, user, ticket["id"]).json()
    assert body == {
        "mode": None,
        "insufficient": True,
        "updated_at": body["updated_at"],
        "results": [],
    }
    assert any("suggestions_failed" in r.getMessage() for r in caplog.records)


def test_empty_kb_snapshot_is_insufficient(client, auth_headers, user):
    ticket = create_ticket(client, auth_headers, user)

    body = suggestions(client, auth_headers, user, ticket["id"]).json()

    assert body["mode"] == "semantic"
    assert body["insufficient"] is True
    assert body["results"] == []


def test_snapshot_falls_back_to_keyword(
    app, client, auth_headers, user, db_session, indexed_kb
):
    app.dependency_overrides[get_vector_store] = lambda: BrokenStore()
    payload = {
        "title": "Conflicted copy files",
        "description": "I keep getting a conflicted copy.",
        "category": "sync",
    }
    ticket = create_ticket(client, auth_headers, user, payload)

    body = suggestions(client, auth_headers, user, ticket["id"]).json()
    assert body["mode"] == "keyword"
    assert body["results"]
    assert {r.retrieval_mode for r in rows(db_session, ticket["id"])} == {"keyword"}


def test_refresh_replaces_the_snapshot(
    client, auth_headers, user, agent, db_session, sample_kb, embedder, vector_store
):
    ticket = create_ticket(client, auth_headers, user)
    before = suggestions(client, auth_headers, user, ticket["id"]).json()
    assert before["insufficient"] is True

    path = sample_kb / "billing-refund-policy.pdf"
    billing = ingest_bytes(
        db_session,
        agent,
        path.name,
        path.read_bytes(),
        max_bytes=10 * 1024 * 1024,
        embedder=embedder,
        store=vector_store,
    )
    response = client.post(
        f"{TICKETS}/{ticket['id']}/suggestions/refresh", headers=auth_headers(agent)
    )

    assert response.status_code == 200
    after = response.json()
    assert after["insufficient"] is False
    assert {hit["document_id"] for hit in after["results"]} == {billing.id}
    assert after["updated_at"] > before["updated_at"]
    assert len(rows(db_session, ticket["id"])) == len(after["results"])

    refresh_url = f"{TICKETS}/{ticket['id']}/suggestions/refresh"
    again = client.post(refresh_url, headers=auth_headers(user))
    assert again.status_code == 200
    assert len(rows(db_session, ticket["id"])) == len(after["results"])  # replaced, not appended


def test_deleting_a_document_removes_its_suggestions(
    client, auth_headers, user, agent, db_session, indexed_kb
):
    ticket = create_ticket(client, auth_headers, user)
    billing = indexed_kb["billing-refund-policy"]
    before = suggestions(client, auth_headers, user, ticket["id"]).json()
    assert billing.id in [h["document_id"] for h in before["results"]]

    client.delete(f"/api/kb/documents/{billing.id}", headers=auth_headers(agent))

    body = suggestions(client, auth_headers, user, ticket["id"]).json()
    assert billing.id not in [h["document_id"] for h in body["results"]]
    assert len(rows(db_session, ticket["id"])) == len(body["results"])
