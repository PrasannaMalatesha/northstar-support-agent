from pathlib import Path

from evals.labeled import CASES, judges_may_score_test, problems, score_handbook


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


def test_judges_do_not_score_the_held_out_split_before_calibration():
    text = Path("results/judge_calibration.md").read_text()
    assert judges_may_score_test(text) is False


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
