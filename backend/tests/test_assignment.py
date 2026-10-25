import pytest
from sqlalchemy import select

from app.models.ticket import Ticket, TicketEvent
from app.models.user import Role


def assign(client, auth_headers, ticket, actor, agent_id):
    return client.post(
        f"/api/tickets/{ticket.id}/assign",
        json={"agent_id": agent_id},
        headers=auth_headers(actor),
    )


def assigned_events(db_session, ticket):
    stmt = (
        select(TicketEvent)
        .where(TicketEvent.ticket_id == ticket.id, TicketEvent.event_type == "assigned")
        .order_by(TicketEvent.id)
    )
    return list(db_session.scalars(stmt))


@pytest.fixture
def other_agent(make_user):
    return make_user(role=Role.agent, full_name="Second Agent")


def test_assign_reassign_unassign(
    client, db_session, user, agent, other_agent, make_ticket, auth_headers
):
    ticket = make_ticket(user)

    first = assign(client, auth_headers, ticket, agent, agent.id)
    second = assign(client, auth_headers, ticket, agent, other_agent.id)
    third = assign(client, auth_headers, ticket, other_agent, None)

    assert first.status_code == 200
    assert first.json()["assigned_to"] == {
        "id": agent.id,
        "full_name": agent.full_name,
        "role": "agent",
    }
    assert second.json()["assigned_to"]["id"] == other_agent.id
    assert third.status_code == 200
    assert third.json()["assigned_to"] is None
    assert db_session.scalar(select(Ticket.assigned_to).where(Ticket.id == ticket.id)) is None

    written = assigned_events(db_session, ticket)
    assert [e.data for e in written] == [
        {"from_agent_id": None, "to_agent_id": agent.id},
        {"from_agent_id": agent.id, "to_agent_id": other_agent.id},
        {"from_agent_id": other_agent.id, "to_agent_id": None},
    ]
    assert [e.actor_id for e in written] == [agent.id, agent.id, other_agent.id]


def test_assignment_bumps_updated_at_and_shows_in_my_queue(
    client, db_session, user, agent, make_ticket, auth_headers
):
    ticket = make_ticket(user)
    before = db_session.scalar(select(Ticket.updated_at).where(Ticket.id == ticket.id))

    assign(client, auth_headers, ticket, agent, agent.id)

    after = db_session.scalar(select(Ticket.updated_at).where(Ticket.id == ticket.id))
    assert after > before
    mine = client.get("/api/tickets?assigned=me", headers=auth_headers(agent)).json()
    assert [item["id"] for item in mine["items"]] == [ticket.id]


def test_assignment_events_are_visible_to_the_owner(client, user, agent, make_ticket, auth_headers):
    ticket = make_ticket(user)
    assign(client, auth_headers, ticket, agent, agent.id)

    url = f"/api/tickets/{ticket.id}/events"
    owner_events = client.get(url, headers=auth_headers(user)).json()

    assert [e["event_type"] for e in owner_events] == ["created", "assigned"]


def test_user_cannot_assign_even_own_ticket(
    client, db_session, user, agent, make_ticket, auth_headers
):
    ticket = make_ticket(user)

    response = assign(client, auth_headers, ticket, user, agent.id)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AGENT_REQUIRED"
    assert assigned_events(db_session, ticket) == []


@pytest.mark.parametrize("target", ["regular_user", "missing"])
def test_assignee_must_be_an_agent(
    client, db_session, user, agent, make_ticket, auth_headers, target
):
    ticket = make_ticket(user)
    agent_id = user.id if target == "regular_user" else 999999

    response = assign(client, auth_headers, ticket, agent, agent_id)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ASSIGNEE_NOT_AGENT"
    assert assigned_events(db_session, ticket) == []


def test_closed_ticket_cannot_be_assigned(
    client, db_session, user, agent, make_ticket, auth_headers
):
    ticket = make_ticket(user, status="closed")

    response = assign(client, auth_headers, ticket, agent, agent.id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TICKET_CLOSED"
    assert assigned_events(db_session, ticket) == []


@pytest.mark.parametrize("current", ["same_agent", "already_unassigned"])
def test_unchanged_assignment_is_conflict(
    client, db_session, user, agent, make_ticket, auth_headers, current
):
    if current == "same_agent":
        ticket, agent_id = make_ticket(user, assigned_to=agent.id), agent.id
    else:
        ticket, agent_id = make_ticket(user), None

    response = assign(client, auth_headers, ticket, agent, agent_id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ASSIGNMENT_UNCHANGED"
    assert assigned_events(db_session, ticket) == []


def test_agent_id_key_is_required(client, user, agent, make_ticket, auth_headers):
    ticket = make_ticket(user)

    response = client.post(
        f"/api/tickets/{ticket.id}/assign", json={}, headers=auth_headers(agent)
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_assign_unknown_ticket_is_404(client, agent, auth_headers):
    response = client.post(
        "/api/tickets/999999/assign", json={"agent_id": agent.id}, headers=auth_headers(agent)
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TICKET_NOT_FOUND"
