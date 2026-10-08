"""A stated contact preference carries to the customer's next case, and never sets an amount (R20)."""

import os

import psycopg

from northstar.preferences import stated

_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://northstar:northstar@localhost:5433/northstar_test")


def _login(client, email: str, password: str) -> dict:
    token = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _forget_everyone() -> None:
    with psycopg.connect(_URL) as conn:
        exists = conn.execute("SELECT to_regclass('public.store')").fetchone()[0]
        if exists:
            conn.execute("DELETE FROM store WHERE prefix LIKE 'customers.%'")


def test_only_a_contact_channel_is_read_from_the_words():
    assert stated("I prefer email, please.") == {"contact_channel": "email"}
    assert stated("Please contact me by text.") == {"contact_channel": "text"}
    assert stated("Use card 4111 1111 1111 1111 next time.") == {}
    assert stated("Do you send order updates by email?") == {}


def test_a_preference_shows_on_the_next_case_and_leaves_the_amount_alone(client, clock):
    _forget_everyone()
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    lead = _login(client, "lead@northstar.example", "northstar-lead")
    client.post("/cases/current/customer", headers=specialist, json={"query": "mira.shah@northstar.example"})
    first = client.post(
        "/cases/current/messages",
        headers=specialist,
        json={"question": "I prefer email. Please refund order NS-1001."},
    ).json()
    assert first["refund_amount_cents"] == 12800
    client.post(f"/approvals/{first['id']}/reject", headers=lead, json={"reason": "Next case."})
    client.post("/cases/current/resolve", headers=specialist, json={"final_text": "Done."})

    clock.advance(seconds=1)
    client.post("/cases/current/new", headers=specialist)
    unbound = client.get("/cases/current", headers=specialist).json()
    assert unbound["preferences"] == {}

    client.post("/cases/current/customer", headers=specialist, json={"query": "mira.shah@northstar.example"})
    second = client.post(
        "/cases/current/messages", headers=specialist, json={"question": "Please refund order NS-1001."}
    ).json()
    assert second["preferences"] == {"contact_channel": "email"}
    assert second["refund_amount_cents"] == 12800
    assert second["policy_citations"] == first["policy_citations"]
    _forget_everyone()
