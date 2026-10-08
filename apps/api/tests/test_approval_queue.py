"""A lead decides from the queue: each row carries the ask, citations, and an order summary (R16)."""

import uuid


def _login(client, email: str, password: str) -> dict:
    token = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_a_queue_row_has_what_the_lead_needs_and_opens_the_case(client):
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    lead = _login(client, "lead@northstar.example", "northstar-lead")
    client.post("/cases/current/customer", headers=specialist, json={"query": "mira.shah@northstar.example"})
    case = client.post("/cases/current/messages", headers=specialist, json={"question": "Please refund order NS-1001."}).json()

    row = client.get("/approvals", headers=lead).json()[0]
    assert row["question"] == "Please refund order NS-1001."
    assert row["citations"] == ["REF-ELIGIBILITY", "REF-CATEGORY"]
    assert row["order_summary"] == "Wool coat, size M. Status: delivered. Total: 12800 cents."

    opened = client.get(f"/cases/{case['id']}", headers=lead)
    assert opened.status_code == 200
    assert opened.json()["messages"][-1]["decision"] == "approve_refund"
    assert client.get(f"/cases/{case['id']}", headers=specialist).status_code == 403
    assert client.get(f"/cases/{uuid.uuid4()}", headers=lead).status_code == 404
    assert client.get("/cases/not-a-case", headers=lead).status_code == 404

    decided = client.post(f"/approvals/{row['case_id']}/approve", headers=lead).json()
    assert decided["ticket_id"]
    assert client.get("/approvals", headers=lead).json() == []
