"""The ticket state machine (docs/PLAN.md §6).

Expectations are written out here, independently of services/workflow.TRANSITIONS, so the table
itself is under test."""

import pytest
from sqlalchemy import select

from app.models.ticket import Ticket, TicketEvent
from app.models.user import Role

STATUSES = ["open", "in_progress", "waiting_for_user", "resolved", "closed"]

# actor -> from status -> statuses that actor may move to, in the order the API lists them.
EXPECTED_ALLOWED = {
    "owner": {
        "open": [],
        "in_progress": [],
        "waiting_for_user": [],
        "resolved": ["closed", "open"],
        "closed": [],
    },
    "agent": {
        "open": ["in_progress", "resolved"],
        "in_progress": ["waiting_for_user", "resolved"],
        "waiting_for_user": ["in_progress", "resolved"],
        "resolved": ["closed"],
        "closed": [],
    },
    # An agent who opened the ticket gets both sets.
    "agent_owner": {
        "open": ["in_progress", "resolved"],
        "in_progress": ["waiting_for_user", "resolved"],
        "waiting_for_user": ["in_progress", "resolved"],
        "resolved": ["closed", "open"],
        "closed": [],
    },
}

VALID = [
    (actor, from_status, to_status)
    for actor in ("owner", "agent")
    for from_status, targets in EXPECTED_ALLOWED[actor].items()
    for to_status in targets
]
INVALID = [
    (actor, from_status, to_status)
    for actor in ("owner", "agent")
    for from_status in STATUSES
    for to_status in STATUSES
    if to_status not in EXPECTED_ALLOWED[actor][from_status]
]


def case_id(case):
    return "{}:{}->{}".format(*case)


@pytest.fixture
def setup_ticket(user, agent, make_ticket):
    """Return (ticket, acting user) for an actor kind and starting status."""

    def _setup(actor: str, status: str):
        if actor == "owner":
            return make_ticket(user, status=status), user
        if actor == "agent":
            return make_ticket(user, status=status), agent
        return make_ticket(agent, status=status), agent  # agent_owner

    return _setup


def events(db_session, ticket):
    stmt = select(TicketEvent).where(TicketEvent.ticket_id == ticket.id).order_by(TicketEvent.id)
    return list(db_session.scalars(stmt))


def current_status(db_session, ticket):
    return db_session.scalar(select(Ticket.status).where(Ticket.id == ticket.id))


def change(client, auth_headers, ticket, actor, status):
    return client.post(
        f"/api/tickets/{ticket.id}/status", json={"status": status}, headers=auth_headers(actor)
    )


# --- transitions ---


@pytest.mark.parametrize("case", VALID, ids=[case_id(c) for c in VALID])
def test_valid_transition(client, db_session, auth_headers, setup_ticket, case):
    actor_kind, from_status, to_status = case
    ticket, actor = setup_ticket(actor_kind, from_status)
    before = db_session.scalar(select(Ticket.updated_at).where(Ticket.id == ticket.id))

    response = change(client, auth_headers, ticket, actor, to_status)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == to_status
    assert body["allowed_transitions"] == EXPECTED_ALLOWED[actor_kind][to_status]
    last = events(db_session, ticket)[-1]
    assert last.event_type == "status_changed"
    assert last.data == {"from": from_status, "to": to_status}
    assert last.actor_id == actor.id
    after = db_session.scalar(select(Ticket.updated_at).where(Ticket.id == ticket.id))
    assert after > before


@pytest.mark.parametrize("case", INVALID, ids=[case_id(c) for c in INVALID])
def test_invalid_transition_is_conflict(client, db_session, auth_headers, setup_ticket, case):
    actor_kind, from_status, to_status = case
    ticket, actor = setup_ticket(actor_kind, from_status)

    response = change(client, auth_headers, ticket, actor, to_status)

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "INVALID_TRANSITION"
    assert error["details"] == {
        "from": from_status,
        "to": to_status,
        "allowed": EXPECTED_ALLOWED[actor_kind][from_status],
    }
    assert current_status(db_session, ticket) == from_status
    assert [e.event_type for e in events(db_session, ticket)] == ["created"]


def test_unknown_status_value_is_422(client, user, make_ticket, auth_headers):
    ticket = make_ticket(user)

    response = change(client, auth_headers, ticket, user, "archived")

    assert response.status_code == 422


def test_full_lifecycle(client, user, agent, make_ticket, auth_headers):
    ticket = make_ticket(user)

    for actor, status in [
        (agent, "in_progress"),
        (agent, "waiting_for_user"),
        (agent, "in_progress"),
        (agent, "resolved"),
        (user, "open"),  # owner reopens
        (agent, "resolved"),
        (user, "closed"),
    ]:
        response = change(client, auth_headers, ticket, actor, status)
        assert response.status_code == 200, (status, response.json())

    final = client.get(f"/api/tickets/{ticket.id}", headers=auth_headers(user)).json()
    assert final["status"] == "closed"
    assert final["allowed_transitions"] == []


# --- allowed_transitions on detail ---


@pytest.mark.parametrize("status", STATUSES)
@pytest.mark.parametrize("actor_kind", ["owner", "agent", "agent_owner"])
def test_allowed_transitions_on_detail(client, auth_headers, setup_ticket, actor_kind, status):
    ticket, actor = setup_ticket(actor_kind, status)

    response = client.get(f"/api/tickets/{ticket.id}", headers=auth_headers(actor))

    assert response.json()["allowed_transitions"] == EXPECTED_ALLOWED[actor_kind][status]


def test_closed_is_terminal_for_everyone(client, user, agent, make_ticket, auth_headers):
    ticket = make_ticket(user, status="closed")

    for actor in (user, agent):
        detail = client.get(f"/api/tickets/{ticket.id}", headers=auth_headers(actor)).json()
        assert detail["allowed_transitions"] == []
        for status in STATUSES:
            assert change(client, auth_headers, ticket, actor, status).status_code == 409


def test_list_items_do_not_carry_allowed_transitions(client, user, make_ticket, auth_headers):
    make_ticket(user)

    item = client.get("/api/tickets", headers=auth_headers(user)).json()["items"][0]

    assert "allowed_transitions" not in item


# --- automatic waiting_for_user -> in_progress ---


def comment(client, auth_headers, ticket, author, body="Here is the info", internal=False):
    return client.post(
        f"/api/tickets/{ticket.id}/comments",
        json={"body": body, "is_internal": internal},
        headers=auth_headers(author),
    )


def test_owner_comment_moves_waiting_ticket_to_in_progress(
    client, db_session, user, make_ticket, auth_headers
):
    ticket = make_ticket(user, status="waiting_for_user")

    response = comment(client, auth_headers, ticket, user)

    assert response.status_code == 201
    assert current_status(db_session, ticket) == "in_progress"
    written = events(db_session, ticket)
    assert [e.event_type for e in written] == ["created", "comment_added", "status_changed"]
    assert written[-1].data == {"from": "waiting_for_user", "to": "in_progress", "automatic": True}
    assert written[-1].actor_id == user.id


@pytest.mark.parametrize("internal", [False, True], ids=["public", "internal"])
def test_agent_comment_does_not_move_waiting_ticket(
    client, db_session, user, agent, make_ticket, auth_headers, internal
):
    ticket = make_ticket(user, status="waiting_for_user")

    response = comment(client, auth_headers, ticket, agent, internal=internal)

    assert response.status_code == 201
    assert current_status(db_session, ticket) == "waiting_for_user"


@pytest.mark.parametrize("status", ["open", "in_progress", "resolved"])
def test_owner_comment_in_other_statuses_changes_nothing(
    client, db_session, user, make_ticket, auth_headers, status
):
    ticket = make_ticket(user, status=status)

    response = comment(client, auth_headers, ticket, user)

    assert response.status_code == 201
    assert current_status(db_session, ticket) == status
    assert "status_changed" not in [e.event_type for e in events(db_session, ticket)]


def test_agent_owner_comment_also_triggers(
    client, db_session, make_user, make_ticket, auth_headers
):
    agent_owner = make_user(role=Role.agent)
    ticket = make_ticket(agent_owner, status="waiting_for_user")

    comment(client, auth_headers, ticket, agent_owner)

    assert current_status(db_session, ticket) == "in_progress"
