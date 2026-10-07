import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from evals.labeled import (
    CASES,
    comparison_text,
    judges_may_score_test,
    problems,
    score_handbook,
    score_naive,
)

_TEST_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://northstar:northstar@localhost:5433/northstar_test",
)
_START = datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc)


def _login(client, email, password):
    token = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _fresh(client, headers, lead_headers, clock):
    body = client.get("/cases/current", headers=headers).json()
    if body["status"] == "Waiting for approval":
        rejected = client.post(
            f"/approvals/{body['id']}/reject",
            headers=lead_headers,
            json={"reason": "Next case."},
        )
        assert rejected.status_code == 200, rejected.text
        body = client.get("/cases/current", headers=headers).json()
    if body["status"] == "Open":
        closed = client.post(
            "/cases/current/resolve",
            headers=headers,
            json={"final_text": "Closed."},
        )
        assert closed.status_code == 200, closed.text
    clock.advance(seconds=1)
    opened = client.post("/cases/current/new", headers=headers)
    assert opened.status_code == 200, opened.text


def test_the_labeled_set_is_frozen_and_cites_the_registry():
    assert problems() == []
    assert len(CASES) == 40


def test_handbook_rows_match_their_labels():
    missed = [row["id"] for row in score_handbook() if not row["passed"]]
    assert missed == []


def test_recorded_agreement_opens_the_held_out_split():
    text = Path("results/judge_calibration.md").read_text()
    assert "agreement: 5/5" in text
    assert "test split: open" in text
    assert judges_may_score_test(text) is True


def test_desk_rows_match_their_labels(client, clock):
    headers = _login(client, "specialist@northstar.example", "northstar-specialist")
    lead_headers = _login(client, "lead@northstar.example", "northstar-lead")
    for case in CASES:
        if case["channel"] != "desk":
            continue
        if case.get("advance_days"):
            clock.advance(days=case["advance_days"])
            headers = _login(client, "specialist@northstar.example", "northstar-specialist")
            lead_headers = _login(client, "lead@northstar.example", "northstar-lead")
        _fresh(client, headers, lead_headers, clock)
        if case["customer"]:
            bound = client.post(
                "/cases/current/customer",
                headers=headers,
                json={"query": case["customer"]},
            )
            assert bound.status_code == 200, bound.text
        response = client.post(
            "/cases/current/messages",
            headers=headers,
            json={"question": case["question"]},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        draft = body["messages"][-1]
        assert draft["decision"] == case["decision"], case["id"]
        for section in case["sections"]:
            assert section in draft["citations"], case["id"]
        assert body["status"] == case["status"], case["id"]
        if case["ticket"] is False:
            assert body["ticket_id"] is None, case["id"]
        if case.get("proposer_blocked"):
            blocked = client.post(f"/approvals/{body['id']}/approve", headers=headers)
            assert blocked.status_code == 403, case["id"]
            assert client.get("/cases/current", headers=headers).json()["ticket_id"] is None


def _clear_cases() -> None:
    with psycopg.connect(_TEST_URL, autocommit=True) as conn:
        conn.execute("DELETE FROM case_messages")
        conn.execute("DELETE FROM tickets")
        conn.execute("DELETE FROM cases")
        conn.execute("DELETE FROM usage_days")


def _desk_passed(client, clock) -> dict[str, bool]:
    _clear_cases()
    clock.moment = _START
    headers = _login(client, "specialist@northstar.example", "northstar-specialist")
    lead_headers = _login(client, "lead@northstar.example", "northstar-lead")
    passed = {}
    for case in CASES:
        if case["split"] != "test" or case["channel"] != "desk":
            continue
        if case.get("advance_days"):
            clock.advance(days=case["advance_days"])
            headers = _login(client, "specialist@northstar.example", "northstar-specialist")
            lead_headers = _login(client, "lead@northstar.example", "northstar-lead")
        _fresh(client, headers, lead_headers, clock)
        if case["customer"]:
            client.post(
                "/cases/current/customer",
                headers=headers,
                json={"query": case["customer"]},
            )
        body = client.post(
            "/cases/current/messages",
            headers=headers,
            json={"question": case["question"]},
        ).json()
        draft = body["messages"][-1]
        ok = (
            draft["decision"] == case["decision"]
            and all(section in draft["citations"] for section in case["sections"])
            and body["status"] == case["status"]
            and (body["ticket_id"] is None or case["ticket"] is not False)
        )
        if case.get("proposer_blocked"):
            blocked = client.post(f"/approvals/{body['id']}/approve", headers=headers)
            ok = ok and blocked.status_code == 403 and body["ticket_id"] is None
        passed[case["id"]] = ok
    return passed


def test_held_out_v0_against_v1_is_recorded(client, clock):
    naive_runs = [score_naive() for _ in range(3)]
    v0_runs = [{row["id"]: row["passed"] for row in run} for run in naive_runs]
    channels = {case["id"]: case["channel"] for case in CASES}
    v1_runs = []
    for _ in range(3):
        desk = _desk_passed(client, clock)
        v1_runs.append(
            {
                row["id"]: row["passed"] if channels[row["id"]] == "handbook" else desk[row["id"]]
                for row in naive_runs[0]
            }
        )
    text = comparison_text(v0_runs, v1_runs, naive_runs[0])
    assert Path("results/v0_v1.md").read_text() == text
