"""An address change waits for a lead, only while the order is placed or packed (SHIP-ADDRESS)."""


def _login(client, email: str, password: str) -> dict:
    token = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_the_lead_sees_the_new_address_and_the_draft_does_not(client):
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    lead = _login(client, "lead@northstar.example", "northstar-lead")
    client.post("/cases/current/customer", headers=specialist, json={"query": "mira.shah@northstar.example"})
    body = client.post(
        "/cases/current/messages",
        headers=specialist,
        json={"question": "Change the address on order NS-1004 to 12 Oak St, Austin TX 78701."},
    ).json()
    assert body["action"] == "address_change"
    assert body["refund_amount_cents"] is None
    assert "12 Oak St" not in body["messages"][-1]["body"]
    row = client.get("/approvals", headers=lead).json()[0]
    assert row["amount_cents"] is None
    assert row["details"] == "New address: 12 Oak St, Austin TX 78701"

    edit = client.post(f"/approvals/{body['id']}/edit", headers=lead, json={"amount_cents": 100})
    assert edit.status_code == 422
    ticket = client.post(f"/approvals/{body['id']}/approve", headers=lead).json()["ticket_id"]
    assert ticket
    assert client.get("/approvals", headers=lead).json() == []
