import logging

import pytest

# (method, path template, json body) for every endpoint that addresses one ticket.
TICKET_ENDPOINTS = [
    ("GET", "/api/tickets/{id}", None),
    ("PATCH", "/api/tickets/{id}", {"title": "Hijacked title"}),
    ("GET", "/api/tickets/{id}/comments", None),
    ("POST", "/api/tickets/{id}/comments", {"body": "Hello from someone else"}),
    ("GET", "/api/tickets/{id}/events", None),
    ("POST", "/api/tickets/{id}/status", {"status": "resolved"}),
    ("GET", "/api/tickets/{id}/suggestions", None),
    ("POST", "/api/tickets/{id}/suggestions/refresh", None),
]

ALL_ENDPOINTS = [
    ("GET", "/api/tickets", None),
    (
        "POST",
        "/api/tickets",
        {"title": "No token", "description": "Should never be created.", "category": "other"},
    ),
    *TICKET_ENDPOINTS,
    ("POST", "/api/tickets/{id}/assign", {"agent_id": None}),
]

ENDPOINT_IDS = [f"{method} {path}" for method, path, _ in TICKET_ENDPOINTS]


@pytest.mark.parametrize(("method", "path", "body"), TICKET_ENDPOINTS, ids=ENDPOINT_IDS)
def test_other_users_ticket_is_indistinguishable_from_missing(
    client, make_user, make_ticket, auth_headers, caplog, method, path, body
):
    owner, intruder = make_user(), make_user()
    ticket = make_ticket(owner)
    headers = auth_headers(intruder)

    with caplog.at_level(logging.WARNING, logger="app.permissions"):
        foreign = client.request(method, path.format(id=ticket.id), json=body, headers=headers)
    missing = client.request(method, path.format(id=999999), json=body, headers=headers)

    assert foreign.status_code == 404
    assert foreign.json() == missing.json()
    assert foreign.json()["error"]["code"] == "TICKET_NOT_FOUND"
    assert any(
        "permission_denied" in r.getMessage() and f"ticket_id={ticket.id}" in r.getMessage()
        for r in caplog.records
    )


def test_other_users_ticket_is_unchanged(client, make_user, make_ticket, auth_headers):
    owner, intruder = make_user(), make_user()
    ticket = make_ticket(owner)
    original_title = ticket.title
    url = f"/api/tickets/{ticket.id}"

    client.patch(url, json={"title": "Hijacked title"}, headers=auth_headers(intruder))
    client.post(f"{url}/comments", json={"body": "spam"}, headers=auth_headers(intruder))

    owner_view = client.get(url, headers=auth_headers(owner)).json()
    comments = client.get(f"{url}/comments", headers=auth_headers(owner)).json()
    assert owner_view["title"] == original_title
    assert comments == []


@pytest.mark.parametrize(
    ("method", "path", "body"),
    ALL_ENDPOINTS,
    ids=[f"{method} {path}" for method, path, _ in ALL_ENDPOINTS],
)
def test_ticket_endpoints_require_token(client, user, make_ticket, method, path, body):
    ticket = make_ticket(user)

    response = client.request(method, path.format(id=ticket.id), json=body)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"
