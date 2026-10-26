import pytest
from sqlalchemy import func, select

from app.models.document import Document
from app.models.suggestion import TicketSuggestion
from app.models.ticket import Ticket, TicketComment, TicketEvent
from app.models.user import Role, User
from scripts.seed import MARKER_EMAIL, seed

PASSWORD = "seed-pass-123"


@pytest.fixture
def run_seed(db_session, embedder, vector_store, sample_kb):
    def _run(**kwargs):
        return seed(
            db_session,
            embedder,
            vector_store,
            sample_kb_dir=sample_kb,
            password=PASSWORD,
            **kwargs,
        )

    return _run


def count(db_session, model, *conditions):
    return db_session.scalar(select(func.count()).select_from(model).where(*conditions))


def totals(db_session):
    return {
        "users": count(db_session, User),
        "documents": count(db_session, Document),
        "tickets": count(db_session, Ticket),
        "comments": count(db_session, TicketComment),
        "events": count(db_session, TicketEvent),
        "suggestions": count(db_session, TicketSuggestion),
    }


def status_changes(db_session):
    stmt = select(TicketEvent).where(TicketEvent.event_type == "status_changed")
    return list(db_session.scalars(stmt))


def test_seed_builds_the_demo(run_seed, db_session, vector_store):
    result = run_seed()

    assert (result.skipped, result.users, result.documents, result.tickets) == (False, 4, 6, 8)
    assert count(db_session, User) == 4
    assert count(db_session, User, User.role == Role.agent) == 2
    assert db_session.scalar(select(User).where(User.email == MARKER_EMAIL)).role == "agent"

    documents = list(db_session.scalars(select(Document)))
    assert len(documents) == 6
    assert all(d.status == "ready" and d.vector_indexed for d in documents)
    assert all(vector_store.count_for_document(d.id) == d.chunk_count for d in documents)

    tickets = list(db_session.scalars(select(Ticket)))
    assert len(tickets) == 8
    assert {t.status for t in tickets} == {
        "open",
        "in_progress",
        "waiting_for_user",
        "resolved",
        "closed",
    }
    assert all(t.suggestions_mode == "semantic" for t in tickets)
    assert count(db_session, TicketSuggestion) > 0
    assert count(db_session, TicketComment, TicketComment.is_internal.is_(True)) >= 2
    assert sum(1 for t in tickets if t.assigned_to is None and t.status == "open") == 2


def test_seed_histories_are_genuine(run_seed, db_session):
    run_seed()
    tickets = {t.id: t for t in db_session.scalars(select(Ticket))}
    changes = status_changes(db_session)

    automatic = [e for e in changes if e.data.get("automatic")]
    assert len(automatic) == 1
    assert automatic[0].data["to"] == "in_progress"
    assert automatic[0].actor_id == tickets[automatic[0].ticket_id].created_by

    closed = [e for e in changes if e.data["to"] == "closed"]
    reopened = [e for e in changes if e.data == {"from": "resolved", "to": "open"}]
    assert len(closed) == len(reopened) == 1
    for event in closed + reopened:  # both done by the ticket's owner
        assert event.actor_id == tickets[event.ticket_id].created_by


def test_seeded_accounts_work(run_seed, client):
    run_seed()

    agent_login = client.post(
        "/api/auth/login", json={"email": "priya@acme-demo.com", "password": PASSWORD}
    )
    user_login = client.post(
        "/api/auth/login", json={"email": "dana@acme-demo.com", "password": PASSWORD}
    )
    assert agent_login.status_code == user_login.status_code == 200

    agent_headers = {"Authorization": f"Bearer {agent_login.json()['access_token']}"}
    user_headers = {"Authorization": f"Bearer {user_login.json()['access_token']}"}
    dashboard = client.get("/api/dashboard/agent", headers=agent_headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["counts"] == {
        "my_open": 4,
        "unassigned": 2,
        "waiting_for_user": 1,
        "urgent": 1,
    }
    assert client.get("/api/dashboard/agent", headers=user_headers).status_code == 403
    assert len(client.get("/api/tickets", headers=user_headers).json()["items"]) == 4


def test_second_run_is_skipped(run_seed, db_session):
    run_seed()
    before = totals(db_session)

    result = run_seed()

    assert result.skipped is True
    assert totals(db_session) == before


def test_reset_wipes_and_reseeds(run_seed, db_session, make_user, vector_store):
    run_seed()
    fresh = totals(db_session)
    make_user(email="hand-made@example.com")

    result = run_seed(reset=True)

    assert result.skipped is False
    assert db_session.scalar(select(User).where(User.email == "hand-made@example.com")) is None
    assert totals(db_session) == fresh
    assert db_session.scalar(select(func.min(Ticket.id))) == 1  # identities restarted
    for document in db_session.scalars(select(Document)):
        assert vector_store.count_for_document(document.id) == document.chunk_count
