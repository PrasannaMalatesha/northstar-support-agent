from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from conftest import TEST_URL
from northstar.cases import CaseStore
from northstar.clock import SystemClock


def _login(client, email: str, password: str) -> str:
    return client.post(
        "/auth/login",
        json={"email": email, "password": password},
    ).json()["access_token"]


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
    assert body["status"] == "Waiting for approval"
    return body["id"]


def test_a_lead_approves_once_and_a_second_approve_returns_the_same_ticket(client, clock):
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    lead = _login(client, "lead@northstar.example", "northstar-lead")
    case_id = _propose(client, specialist)

    refused = client.get("/approvals", headers={"Authorization": f"Bearer {specialist}"})
    assert refused.status_code == 403
    specialist_decide = client.post(
        f"/approvals/{case_id}/approve",
        headers={"Authorization": f"Bearer {specialist}"},
    )
    assert specialist_decide.status_code == 403

    clock.advance(seconds=90)
    waiting = client.get("/approvals", headers={"Authorization": f"Bearer {lead}"}).json()
    row = next(item for item in waiting if item["case_id"] == case_id)
    assert row["action"] == "approve_refund"
    assert row["amount_cents"] == 12800
    assert row["order_id"] == "NS-1001"
    assert row["age_seconds"] >= 90

    approved = client.post(
        f"/approvals/{case_id}/approve",
        headers={"Authorization": f"Bearer {lead}"},
    )
    assert approved.status_code == 200
    ticket_id = approved.json()["ticket_id"]
    assert ticket_id
    again = client.post(
        f"/approvals/{case_id}/approve",
        headers={"Authorization": f"Bearer {lead}"},
    )
    assert again.json()["ticket_id"] == ticket_id
    still = client.get("/approvals", headers={"Authorization": f"Bearer {lead}"}).json()
    assert case_id not in [item["case_id"] for item in still]


def test_the_person_who_proposed_cannot_approve(client):
    lead = _login(client, "lead@northstar.example", "northstar-lead")
    case_id = _propose(client, lead)
    decided = client.post(
        f"/approvals/{case_id}/approve",
        headers={"Authorization": f"Bearer {lead}"},
    )
    assert decided.status_code == 403
    assert client.get("/approvals", headers={"Authorization": f"Bearer {lead}"}).json()[0]["case_id"] == case_id


def test_a_new_process_still_sees_the_waiting_proposal(client):
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    case_id = _propose(client, specialist)
    pool = ConnectionPool(TEST_URL, min_size=1, max_size=1, kwargs={"row_factory": dict_row}, open=True)
    try:
        waiting = CaseStore(pool, SystemClock()).pending()
    finally:
        pool.close()
    assert case_id in [item["case_id"] for item in waiting]
