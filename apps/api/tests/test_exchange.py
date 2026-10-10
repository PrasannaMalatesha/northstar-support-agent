"""An exchange is the same item in another size, in stock, once per line (EXC-*)."""


def _login(client, email: str, password: str) -> dict:
    token = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_an_exchange_is_offered_once_per_line(client):
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    lead = _login(client, "lead@northstar.example", "northstar-lead")
    client.post("/cases/current/customer", headers=specialist, json={"query": "mira.shah@northstar.example"})
    body = client.post(
        "/cases/current/messages", headers=specialist, json={"question": "Exchange order NS-1001 for size L."}
    ).json()
    assert body["action"] == "exchange"
    assert body["proposal_details"] == "Wool coat: size M to size L"
    assert body["refund_amount_cents"] is None
    assert client.post(f"/approvals/{body['id']}/approve", headers=lead).json()["ticket_id"]

    again = client.post(
        "/cases/current/messages", headers=specialist, json={"question": "Now exchange order NS-1001 for size S."}
    ).json()
    draft = again["messages"][-1]
    assert draft["decision"] == "answer"
    assert draft["citations"] == ["EXC-LIMIT"]
    assert again["status"] == "Open"


def test_a_size_the_item_is_not_made_in_is_named_and_nothing_is_proposed(client):
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    client.post("/cases/current/customer", headers=specialist, json={"query": "mira.shah@northstar.example"})
    body = client.post(
        "/cases/current/messages", headers=specialist, json={"question": "Exchange the wool coat on NS-1001 for an XL."}
    ).json()
    draft = body["messages"][-1]
    assert draft["citations"] == ["EXC-STOCK"]
    assert "not made in size XL" in draft["body"] and "S, M, L" in draft["body"]
    assert body["status"] == "Open"


def test_a_size_without_the_word_size_is_understood():
    from northstar.actions import _wanted_size

    assert _wanted_size("Exchange it for an XL.") == "XL"
    assert _wanted_size("Swap to a M please.") == "M"
    assert _wanted_size("Exchange order NS-1001 for size L.") == "L"
    assert _wanted_size("Exchange for a medium.") == "M"
    assert _wanted_size("Can I exchange it?") is None
