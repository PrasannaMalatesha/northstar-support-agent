def _token(client) -> str:
    return client.post(
        "/auth/login",
        json={"email": "specialist@northstar.example", "password": "northstar-specialist"},
    ).json()["access_token"]


def _bind(client, token: str, query: str) -> None:
    client.post(
        "/cases/current/customer",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": query},
    )


def test_an_owned_order_returns_only_the_record(client):
    token = _token(client)
    _bind(client, token, "mira.shah@northstar.example")
    headers = {"Authorization": f"Bearer {token}"}
    owned = client.post(
        "/cases/current/messages",
        headers=headers,
        json={"question": "What is the status of order NS-1001?"},
    ).json()["messages"][-1]
    assert owned["body"] == (
        "Status: delivered. Purchased: 2026-09-01. "
        "Lines: Wool coat, size M. Prior refunds: none."
    )
    assert owned["citations"] == []

    tracking = client.post(
        "/cases/current/messages",
        headers=headers,
        json={"question": "What is the tracking number for NS-1001?"},
    ).json()["messages"][-1]["body"]
    assert "does not include tracking" in tracking
    assert "Wool coat" in tracking
    assert "1Z" not in tracking


def test_someone_elses_order_and_an_unknown_id_give_no_details(client):
    token = _token(client)
    _bind(client, token, "mira.shah@northstar.example")
    headers = {"Authorization": f"Bearer {token}"}
    other = client.post(
        "/cases/current/messages",
        headers=headers,
        json={"question": "Where is order NS-1002?"},
    ).json()["messages"][-1]["body"]
    assert other == "Not found for this customer."
    assert "Canvas tote" not in other

    unknown = client.post(
        "/cases/current/messages",
        headers=headers,
        json={"question": "Where is order NS-9999?"},
    ).json()["messages"][-1]["body"]
    assert unknown == "That order id is unknown."
