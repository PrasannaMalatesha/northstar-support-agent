def _login(client, email: str, password: str) -> str:
    return client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]


def _propose(client, token: str) -> str:
    headers = {"Authorization": f"Bearer {token}"}
    client.post(
        "/cases/current/customer",
        headers=headers,
        json={"query": "mira.shah@northstar.example"},
    )
    body = client.post(
        "/cases/current/messages",
        headers=headers,
        json={"question": "Please refund order NS-1001."},
    ).json()
    return body["id"]


def test_edit_amount_creates_one_ticket_for_that_amount(client):
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    lead = _login(client, "lead@northstar.example", "northstar-lead")
    case_id = _propose(client, specialist)
    headers = {"Authorization": f"Bearer {lead}"}
    too_high = client.post(
        f"/approvals/{case_id}/edit",
        headers=headers,
        json={"amount_cents": 999999},
    )
    assert too_high.status_code == 422
    edited = client.post(
        f"/approvals/{case_id}/edit",
        headers=headers,
        json={"amount_cents": 5000},
    )
    assert edited.status_code == 200
    assert edited.json()["amount_cents"] == 5000
    ticket_id = edited.json()["ticket_id"]
    again = client.post(
        f"/approvals/{case_id}/edit",
        headers=headers,
        json={"amount_cents": 1000},
    )
    assert again.json()["ticket_id"] == ticket_id
    assert again.json()["amount_cents"] == 5000


def test_reject_records_a_reason_and_creates_no_ticket(client):
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    lead = _login(client, "lead@northstar.example", "northstar-lead")
    case_id = _propose(client, specialist)
    missing = client.post(
        f"/approvals/{case_id}/reject",
        headers={"Authorization": f"Bearer {lead}"},
        json={"reason": ""},
    )
    assert missing.status_code == 422
    rejected = client.post(
        f"/approvals/{case_id}/reject",
        headers={"Authorization": f"Bearer {lead}"},
        json={"reason": "The coat was worn."},
    )
    assert rejected.status_code == 200
    assert rejected.json()["ticket_id"] is None
    case = client.get(
        "/cases/current",
        headers={"Authorization": f"Bearer {specialist}"},
    ).json()
    assert case["ticket_id"] is None
    assert case["rejection_reason"] == "The coat was worn."
    assert case["status"] == "Open"


def test_a_day_old_proposal_is_stale_and_still_waiting(client, clock):
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    lead = _login(client, "lead@northstar.example", "northstar-lead")
    case_id = _propose(client, specialist)
    clock.advance(hours=24, seconds=1)
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    lead = _login(client, "lead@northstar.example", "northstar-lead")
    waiting = client.get("/approvals", headers={"Authorization": f"Bearer {lead}"}).json()
    row = next(item for item in waiting if item["case_id"] == case_id)
    assert row["stale"] is True
    case = client.get(
        "/cases/current",
        headers={"Authorization": f"Bearer {specialist}"},
    ).json()
    assert case["stale"] is True
    assert case["status"] == "Waiting for approval"
    assert case["ticket_id"] is None
