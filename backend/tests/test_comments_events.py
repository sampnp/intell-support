import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError

from app.models.ticket import Ticket, TicketEvent


def comments_url(ticket):
    return f"/api/tickets/{ticket.id}/comments"


def events_url(ticket):
    return f"/api/tickets/{ticket.id}/events"


def updated_at(db_session, ticket):
    return db_session.scalar(select(Ticket.updated_at).where(Ticket.id == ticket.id))


# --- posting ---


def test_owner_comments_on_own_ticket(client, db_session, user, make_ticket, auth_headers):
    ticket = make_ticket(user)
    before = updated_at(db_session, ticket)

    response = client.post(
        comments_url(ticket), json={"body": "  Any update?  "}, headers=auth_headers(user)
    )

    assert response.status_code == 201
    body = response.json()
    assert body["body"] == "Any update?"
    assert body["is_internal"] is False
    assert body["author"]["id"] == user.id
    assert updated_at(db_session, ticket) > before

    events = client.get(events_url(ticket), headers=auth_headers(user)).json()
    assert [e["event_type"] for e in events] == ["created", "comment_added"]
    assert events[-1]["data"] == {"comment_id": body["id"]}
    assert events[-1]["actor"]["id"] == user.id


def test_agent_public_reply(client, user, agent, make_ticket, auth_headers):
    ticket = make_ticket(user)

    response = client.post(
        comments_url(ticket), json={"body": "Looking into it."}, headers=auth_headers(agent)
    )

    assert response.status_code == 201
    assert response.json()["author"]["role"] == "agent"
    comments = client.get(comments_url(ticket), headers=auth_headers(user)).json()
    assert [c["body"] for c in comments] == ["Looking into it."]


def test_agent_internal_note(client, user, agent, make_ticket, auth_headers):
    ticket = make_ticket(user)

    response = client.post(
        comments_url(ticket),
        json={"body": "Customer is on the legacy plan.", "is_internal": True},
        headers=auth_headers(agent),
    )

    assert response.status_code == 201
    assert response.json()["is_internal"] is True
    events = client.get(events_url(ticket), headers=auth_headers(agent)).json()
    assert events[-1]["event_type"] == "internal_note_added"


def test_user_cannot_post_internal_note(client, user, make_ticket, auth_headers):
    ticket = make_ticket(user)

    response = client.post(
        comments_url(ticket),
        json={"body": "sneaky", "is_internal": True},
        headers=auth_headers(user),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INTERNAL_NOTE_FORBIDDEN"
    assert client.get(comments_url(ticket), headers=auth_headers(user)).json() == []


@pytest.mark.parametrize("commenter", ["user", "agent"])
def test_closed_ticket_takes_no_comments(
    request, client, user, make_ticket, auth_headers, commenter
):
    ticket = make_ticket(user, status="closed")
    author = request.getfixturevalue(commenter)

    response = client.post(
        comments_url(ticket), json={"body": "Hello?"}, headers=auth_headers(author)
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TICKET_CLOSED"


def test_resolved_ticket_still_takes_comments(client, user, make_ticket, auth_headers):
    ticket = make_ticket(user, status="resolved")

    response = client.post(
        comments_url(ticket), json={"body": "Still broken, sorry."}, headers=auth_headers(user)
    )

    assert response.status_code == 201


@pytest.mark.parametrize("body", [{"body": ""}, {"body": "   "}, {"body": "x" * 5001}, {}])
def test_comment_validation(client, user, make_ticket, auth_headers, body):
    ticket = make_ticket(user)

    response = client.post(comments_url(ticket), json=body, headers=auth_headers(user))

    assert response.status_code == 422


# --- visibility ---


@pytest.fixture
def conversation(client, user, agent, make_ticket, auth_headers):
    """A ticket with a public reply, an internal note and an owner comment, in that order."""
    ticket = make_ticket(user)
    for author, body, internal in [
        (agent, "Public reply", False),
        (agent, "Internal note", True),
        (user, "Owner comment", False),
    ]:
        response = client.post(
            comments_url(ticket),
            json={"body": body, "is_internal": internal},
            headers=auth_headers(author),
        )
        assert response.status_code == 201
    return ticket


def test_user_never_sees_internal_notes(client, user, auth_headers, conversation):
    comments = client.get(comments_url(conversation), headers=auth_headers(user)).json()
    events = client.get(events_url(conversation), headers=auth_headers(user)).json()

    assert [c["body"] for c in comments] == ["Public reply", "Owner comment"]
    assert all(not c["is_internal"] for c in comments)
    assert [e["event_type"] for e in events] == ["created", "comment_added", "comment_added"]


def test_agent_sees_everything_oldest_first(client, agent, auth_headers, conversation):
    comments = client.get(comments_url(conversation), headers=auth_headers(agent)).json()
    events = client.get(events_url(conversation), headers=auth_headers(agent)).json()

    assert [c["body"] for c in comments] == ["Public reply", "Internal note", "Owner comment"]
    assert [e["event_type"] for e in events] == [
        "created",
        "comment_added",
        "internal_note_added",
        "comment_added",
    ]


# --- append-only ---


@pytest.mark.parametrize(
    "statement",
    [
        update(TicketEvent).values(data={"tampered": True}),
        delete(TicketEvent),
    ],
    ids=["update", "delete"],
)
def test_ticket_events_are_append_only(db_session, user, make_ticket, statement):
    ticket = make_ticket(user)

    with pytest.raises(DBAPIError, match="append-only"):
        with db_session.begin_nested():
            db_session.execute(statement.where(TicketEvent.ticket_id == ticket.id))

    count = db_session.scalar(
        text("SELECT count(*) FROM ticket_events WHERE ticket_id = :id"), {"id": ticket.id}
    )
    assert count == 1
