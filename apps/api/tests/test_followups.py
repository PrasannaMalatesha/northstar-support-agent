import os

import psycopg

_TEST_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://northstar:northstar@localhost:5433/northstar_test",
)


def _login(client, email, password):
    token = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_approval_is_audited_and_a_second_refund_is_denied(client, clock):
    headers = _login(client, "specialist@northstar.example", "northstar-specialist")
    lead = _login(client, "lead@northstar.example", "northstar-lead")
    client.post("/cases/current/customer", headers=headers, json={"query": "mira.shah@northstar.example"})
    first = client.post(
        "/cases/current/messages",
        headers=headers,
        json={"question": "Please refund order NS-1001."},
    ).json()
    waiting = client.get("/approvals", headers=lead).json()
    assert waiting[0]["question"] == "Please refund order NS-1001."
    assert "12800" in waiting[0]["draft"]

    rejected = client.post(
        f"/approvals/{first['id']}/reject",
        headers=lead,
        json={"reason": "Not yet."},
    )
    assert rejected.status_code == 200
    assert client.get("/cases/current", headers=headers).json()["ticket_id"] is None

    again = client.post(
        "/cases/current/messages",
        headers=headers,
        json={"question": "Please refund order NS-1001."},
    ).json()
    approved = client.post(f"/approvals/{again['id']}/approve", headers=lead)
    ticket_id = approved.json()["ticket_id"]
    assert approved.status_code == 200
    assert ticket_id
    replay = client.post(f"/approvals/{again['id']}/approve", headers=lead)
    assert replay.json()["ticket_id"] == ticket_id
    current = client.get("/cases/current", headers=headers).json()
    assert current["ticket_id"] == ticket_id

    clock.advance(seconds=1)
    client.post(
        "/cases/current/resolve",
        headers=headers,
        json={"final_text": "Refunded."},
    )
    clock.advance(seconds=1)
    client.post("/cases/current/new", headers=headers)
    client.post("/cases/current/customer", headers=headers, json={"query": "mira.shah@northstar.example"})
    duplicate = client.post(
        "/cases/current/messages",
        headers=headers,
        json={"question": "Please refund order NS-1001 again."},
    ).json()
    # R15: the refund ticket already exists, so no new proposal is made and the ticket is named (R6 holds).
    assert duplicate["messages"][-1]["decision"] == "duplicate"
    assert ticket_id in duplicate["messages"][-1]["body"]
    assert duplicate["action"] is None
    assert duplicate["ticket_id"] is None

    with psycopg.connect(_TEST_URL) as conn:
        events = [row[0] for row in conn.execute("SELECT event FROM audit_log ORDER BY created_at").fetchall()]
    assert "reject" in events
    assert events.count("approve") == 2
