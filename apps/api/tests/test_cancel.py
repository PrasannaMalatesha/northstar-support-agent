"""A cancel waits for a lead. Only a placed order can be cancelled (ORD-CANCEL)."""


def _login(client, email: str, password: str) -> dict:
    token = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _propose_cancel(client) -> tuple[dict, dict, dict]:
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    lead = _login(client, "lead@northstar.example", "northstar-lead")
    client.post("/cases/current/customer", headers=specialist, json={"query": "mira.shah@northstar.example"})
    body = client.post("/cases/current/messages", headers=specialist, json={"question": "Please cancel order NS-1004."}).json()
    return specialist, lead, body


def test_an_approved_cancel_records_one_ticket_for_the_full_amount(client):
    specialist, lead, body = _propose_cancel(client)
    assert body["action"] == "cancel"
    assert body["refund_amount_cents"] == 6400
    assert body["policy_citations"] == ["ORD-CANCEL"]
    assert client.post(f"/approvals/{body['id']}/approve", headers=specialist).status_code == 403
    first = client.post(f"/approvals/{body['id']}/approve", headers=lead).json()["ticket_id"]
    again = client.post(f"/approvals/{body['id']}/approve", headers=lead).json()["ticket_id"]
    assert first and first == again
    assert client.get("/cases/current", headers=specialist).json()["ticket_id"] == first


def test_a_rejected_cancel_records_the_reason_and_no_ticket(client):
    specialist, lead, body = _propose_cancel(client)
    rejected = client.post(f"/approvals/{body['id']}/reject", headers=lead, json={"reason": "Customer changed their mind."})
    assert rejected.status_code == 200
    case = client.get("/cases/current", headers=specialist).json()
    assert case["ticket_id"] is None
    assert case["rejection_reason"] == "Customer changed their mind."
    assert case["status"] == "Open"


def test_a_cancel_policy_question_without_an_order_is_a_handbook_question(client):
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    # Bound, because an unbound case refuses any order question (R29).
    client.post("/cases/current/customer", headers=specialist, json={"query": "mira.shah@northstar.example"})
    body = client.post(
        "/cases/current/messages",
        headers=specialist,
        json={"question": "Can an order be cancelled after it ships?"},
    ).json()
    assert body["messages"][-1]["decision"] in {"answer", "abstain"}
    assert body["status"] == "Open"
