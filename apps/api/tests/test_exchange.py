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
