from datetime import UTC, datetime

from app.models.user import Role

DASHBOARD = "/api/dashboard/agent"


def ids(items):
    return [item["id"] for item in items]


def test_counts_and_queues(client, auth_headers, make_user, make_ticket, user, agent):
    other_agent = make_user(role=Role.agent)
    mine_open = make_ticket(user, assigned_to=agent.id, priority="low")
    mine_in_progress = make_ticket(
        user, status="in_progress", assigned_to=agent.id, priority="urgent"
    )
    mine_waiting = make_ticket(user, status="waiting_for_user", assigned_to=agent.id)
    make_ticket(user, status="resolved", assigned_to=agent.id)  # not active
    make_ticket(user, status="waiting_for_user", assigned_to=other_agent.id, priority="urgent")
    unassigned_open = make_ticket(user, priority="high")
    make_ticket(user, status="resolved", priority="urgent")  # unassigned but not active
    make_ticket(user, status="closed", priority="urgent")  # not active

    response = client.get(DASHBOARD, headers=auth_headers(agent))

    assert response.status_code == 200
    body = response.json()
    assert body["counts"] == {
        "my_open": 3,  # mine: open, in_progress, waiting
        "unassigned": 1,  # the resolved and closed unassigned tickets don't count
        "waiting_for_user": 2,  # whole team
        "urgent": 2,  # whole team, active only
    }
    assert ids(body["my_queue"]) == [mine_in_progress.id, mine_waiting.id, mine_open.id]
    assert ids(body["unassigned"]) == [unassigned_open.id]


def test_my_queue_is_personal(client, auth_headers, make_user, make_ticket, user, agent):
    other_agent = make_user(role=Role.agent)
    make_ticket(user, status="in_progress", assigned_to=other_agent.id)

    body = client.get(DASHBOARD, headers=auth_headers(agent)).json()

    assert body["my_queue"] == []
    assert body["counts"]["my_open"] == 0


def test_queue_order_is_priority_then_most_recently_updated(
    client, auth_headers, make_ticket, user, agent
):
    older = make_ticket(user, updated_at=datetime(2026, 1, 1, tzinfo=UTC))
    newer = make_ticket(user, updated_at=datetime(2026, 2, 1, tzinfo=UTC))
    newest_low = make_ticket(user, priority="low", updated_at=datetime(2026, 3, 1, tzinfo=UTC))
    urgent = make_ticket(user, priority="urgent", updated_at=datetime(2025, 1, 1, tzinfo=UTC))

    body = client.get(DASHBOARD, headers=auth_headers(agent)).json()

    assert ids(body["unassigned"]) == [urgent.id, newer.id, older.id, newest_low.id]


def test_queues_are_capped_but_counts_are_not(client, auth_headers, make_ticket, user, agent):
    for _ in range(22):
        make_ticket(user)

    body = client.get(DASHBOARD, headers=auth_headers(agent)).json()

    assert body["counts"]["unassigned"] == 22
    assert len(body["unassigned"]) == 20


def test_queue_items_are_summaries(client, auth_headers, make_ticket, user, agent):
    make_ticket(user, assigned_to=agent.id)

    item = client.get(DASHBOARD, headers=auth_headers(agent)).json()["my_queue"][0]

    assert "description" not in item
    assert item["assigned_to"]["id"] == agent.id
    assert item["created_by"]["id"] == user.id


def test_dashboard_is_agent_only(client, auth_headers, user):
    response = client.get(DASHBOARD, headers=auth_headers(user))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AGENT_REQUIRED"
    assert client.get(DASHBOARD).status_code == 401
