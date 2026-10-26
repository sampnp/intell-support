from app.models.user import Role

AGENTS = "/api/users/agents"


def test_lists_only_agents_sorted_by_name(client, auth_headers, make_user, user, agent):
    zoe = make_user(role=Role.agent, full_name="Zoe Agent")
    adam = make_user(role=Role.agent, full_name="Adam Agent")

    response = client.get(AGENTS, headers=auth_headers(agent))

    assert response.status_code == 200
    assert response.json() == [
        {"id": adam.id, "full_name": "Adam Agent", "role": "agent"},
        {"id": agent.id, "full_name": "Support Agent", "role": "agent"},
        {"id": zoe.id, "full_name": "Zoe Agent", "role": "agent"},
    ]
    assert user.id not in [a["id"] for a in response.json()]


def test_agents_list_is_agent_only(client, auth_headers, user):
    response = client.get(AGENTS, headers=auth_headers(user))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AGENT_REQUIRED"
    assert client.get(AGENTS).status_code == 401
