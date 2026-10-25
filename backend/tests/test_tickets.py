import pytest
from sqlalchemy import select

from app.models.ticket import TicketEvent

TICKETS = "/api/tickets"


def ticket_payload(**overrides):
    payload = {
        "title": "Cannot log in",
        "description": "I reset my password but the login page still rejects it.",
        "category": "account",
    }
    payload.update(overrides)
    return payload


def event_types(db_session, ticket_id):
    stmt = (
        select(TicketEvent.event_type)
        .where(TicketEvent.ticket_id == ticket_id)
        .order_by(TicketEvent.id)
    )
    return list(db_session.scalars(stmt))


def ids(response):
    return [item["id"] for item in response.json()["items"]]


# --- create ---


def test_create_ticket(client, db_session, user, auth_headers):
    response = client.post(TICKETS, json=ticket_payload(), headers=auth_headers(user))

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Cannot log in"
    assert body["category"] == "account"
    assert body["priority"] == "medium"
    assert body["status"] == "open"
    assert body["created_by"] == {"id": user.id, "full_name": user.full_name, "role": "user"}
    assert body["assigned_to"] is None
    assert event_types(db_session, body["id"]) == ["created"]


def test_create_ticket_with_chosen_priority(client, user, auth_headers):
    response = client.post(
        TICKETS, json=ticket_payload(priority="urgent"), headers=auth_headers(user)
    )

    assert response.status_code == 201
    assert response.json()["priority"] == "urgent"


def test_create_ticket_ignores_status_and_assignee(client, user, agent, auth_headers):
    payload = ticket_payload(status="resolved", assigned_to=agent.id)

    response = client.post(TICKETS, json=payload, headers=auth_headers(user))

    assert response.status_code == 201
    assert response.json()["status"] == "open"
    assert response.json()["assigned_to"] is None


def test_create_ticket_strips_whitespace(client, user, auth_headers):
    payload = ticket_payload(title="   Cannot log in   ", description="  " + "x" * 10 + "  ")

    response = client.post(TICKETS, json=payload, headers=auth_headers(user))

    assert response.status_code == 201
    assert response.json()["title"] == "Cannot log in"
    assert response.json()["description"] == "x" * 10


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"title": "Hi"}, "title"),
        ({"title": "x" * 201}, "title"),
        ({"title": "     Hi     "}, "title"),
        ({"description": "too short"}, "description"),
        ({"description": "x" * 5001}, "description"),
        ({"category": "hardware"}, "category"),
        ({"priority": "critical"}, "priority"),
    ],
)
def test_create_ticket_validation(client, user, auth_headers, overrides, field):
    response = client.post(TICKETS, json=ticket_payload(**overrides), headers=auth_headers(user))

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"][0]["loc"] == ["body", field]


# --- detail ---


def test_owner_and_agent_can_read_ticket(client, user, agent, make_ticket, auth_headers):
    ticket = make_ticket(user)

    for reader in (user, agent):
        response = client.get(f"{TICKETS}/{ticket.id}", headers=auth_headers(reader))
        assert response.status_code == 200
        assert response.json()["id"] == ticket.id
        assert response.json()["description"] == ticket.description


def test_unknown_ticket_is_404(client, agent, auth_headers):
    response = client.get(f"{TICKETS}/999999", headers=auth_headers(agent))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TICKET_NOT_FOUND"


# --- list ---


def test_user_lists_only_own_tickets(client, make_user, agent, make_ticket, auth_headers):
    alice, bob = make_user(), make_user()
    alice_ticket = make_ticket(alice)
    bob_ticket = make_ticket(bob)

    alice_view = client.get(TICKETS, headers=auth_headers(alice))
    agent_view = client.get(TICKETS, headers=auth_headers(agent))

    assert ids(alice_view) == [alice_ticket.id]
    assert alice_view.json()["total"] == 1
    assert set(ids(agent_view)) >= {alice_ticket.id, bob_ticket.id}


def test_list_items_have_no_description(client, user, make_ticket, auth_headers):
    make_ticket(user)

    item = client.get(TICKETS, headers=auth_headers(user)).json()["items"][0]

    assert "description" not in item
    assert item["created_by"]["id"] == user.id


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("status=resolved", "resolved"),
        ("priority=urgent", "urgent"),
        ("category=billing", "billing"),
    ],
)
def test_list_filters(client, user, make_ticket, auth_headers, query, expected):
    tickets = {
        "plain": make_ticket(user),
        "resolved": make_ticket(user, status="resolved"),
        "urgent": make_ticket(user, priority="urgent"),
        "billing": make_ticket(user, category="billing"),
    }

    response = client.get(f"{TICKETS}?{query}", headers=auth_headers(user))

    assert response.status_code == 200
    assert ids(response) == [tickets[expected].id]


def test_list_assigned_filter(client, user, agent, make_ticket, auth_headers):
    mine = make_ticket(user, assigned_to=agent.id)
    unassigned = make_ticket(user)

    assigned_to_me = client.get(f"{TICKETS}?assigned=me", headers=auth_headers(agent))
    not_assigned = client.get(f"{TICKETS}?assigned=unassigned", headers=auth_headers(agent))

    assert mine.id in ids(assigned_to_me)
    assert unassigned.id not in ids(assigned_to_me)
    assert unassigned.id in ids(not_assigned)
    assert mine.id not in ids(not_assigned)
    assert assigned_to_me.json()["items"][0]["assigned_to"]["id"] == agent.id


def test_list_rejects_bad_filter_values(client, user, auth_headers):
    for query in ("status=pending", "assigned=someone", "page=0", "page_size=101"):
        response = client.get(f"{TICKETS}?{query}", headers=auth_headers(user))
        assert response.status_code == 422, query


@pytest.fixture
def searchable(user, make_ticket):
    return {
        "sync": make_ticket(user),  # "Cannot sync my files" / "...stuck on 'syncing'..."
        "billing": make_ticket(
            user,
            title="Invoice charged twice",
            description="My credit card was billed two times for the same invoice.",
            category="billing",
        ),
    }


@pytest.mark.parametrize(
    ("q", "expected"),
    [
        ("invoice", ["billing"]),  # title
        ("credit card", ["billing"]),  # description
        ("synced", ["sync"]),  # stemming: synced / syncing / sync
        ("zebra quantum", []),
    ],
)
def test_list_search(client, user, auth_headers, searchable, q, expected):
    response = client.get(TICKETS, params={"q": q}, headers=auth_headers(user))

    assert response.status_code == 200
    assert ids(response) == [searchable[name].id for name in expected]
    assert response.json()["total"] == len(expected)


def test_blank_search_is_ignored(client, user, auth_headers, searchable):
    response = client.get(TICKETS, params={"q": "   "}, headers=auth_headers(user))

    assert response.json()["total"] == 2


def test_list_pagination(client, user, make_ticket, auth_headers):
    created = [make_ticket(user) for _ in range(3)]

    page1 = client.get(f"{TICKETS}?page_size=2&page=1", headers=auth_headers(user)).json()
    page2 = client.get(f"{TICKETS}?page_size=2&page=2", headers=auth_headers(user)).json()

    assert (page1["total"], page1["page"], page1["page_size"]) == (3, 1, 2)
    assert len(page1["items"]) == 2
    assert len(page2["items"]) == 1
    all_ids = [item["id"] for item in page1["items"] + page2["items"]]
    assert sorted(all_ids) == sorted(t.id for t in created)


def test_list_orders_by_most_recently_updated(client, user, make_ticket, auth_headers):
    older, newer = make_ticket(user), make_ticket(user)
    headers = auth_headers(user)

    # Same updated_at inside the test transaction: newest id first.
    assert ids(client.get(TICKETS, headers=headers)) == [newer.id, older.id]

    client.patch(f"{TICKETS}/{older.id}", json={"title": "Edited title"}, headers=headers)

    assert ids(client.get(TICKETS, headers=headers)) == [older.id, newer.id]


# --- patch ---


def test_owner_edits_open_ticket(client, db_session, user, make_ticket, auth_headers):
    ticket = make_ticket(user)

    response = client.patch(
        f"{TICKETS}/{ticket.id}",
        json={"title": "  New title here  ", "description": ticket.description},
        headers=auth_headers(user),
    )

    assert response.status_code == 200
    assert response.json()["title"] == "New title here"
    assert event_types(db_session, ticket.id) == ["created", "ticket_updated"]
    updated = db_session.scalars(
        select(TicketEvent).where(TicketEvent.event_type == "ticket_updated")
    ).one()
    assert updated.data == {"fields": ["title"]}
    assert updated.actor_id == user.id


def test_edit_with_unchanged_values_writes_no_event(
    client, db_session, user, make_ticket, auth_headers
):
    ticket = make_ticket(user)

    response = client.patch(
        f"{TICKETS}/{ticket.id}", json={"title": ticket.title}, headers=auth_headers(user)
    )

    assert response.status_code == 200
    assert event_types(db_session, ticket.id) == ["created"]


@pytest.mark.parametrize("body", [{}, {"title": None}, {"description": "short"}])
def test_edit_validation(client, user, make_ticket, auth_headers, body):
    ticket = make_ticket(user)

    response = client.patch(f"{TICKETS}/{ticket.id}", json=body, headers=auth_headers(user))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_agent_cannot_edit(client, user, agent, make_ticket, auth_headers):
    ticket = make_ticket(user)

    response = client.patch(
        f"{TICKETS}/{ticket.id}", json={"title": "Agent edit"}, headers=auth_headers(agent)
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "TICKET_EDIT_FORBIDDEN"


@pytest.mark.parametrize("status", ["in_progress", "waiting_for_user", "resolved", "closed"])
def test_owner_cannot_edit_non_open_ticket(client, user, make_ticket, auth_headers, status):
    ticket = make_ticket(user, status=status)

    response = client.patch(
        f"{TICKETS}/{ticket.id}", json={"title": "Too late now"}, headers=auth_headers(user)
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TICKET_NOT_EDITABLE"
