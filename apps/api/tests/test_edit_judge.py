"""Every specialist edit and every handoff escalation reaches the groundedness judge."""

import os

import psycopg
import pytest

import northstar.online as online
from northstar.memory import graph_for
from northstar.online import record_judge

_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://northstar:northstar@localhost:5433/northstar_test",
)


@pytest.fixture()
def judged(monkeypatch):
    seen = {"graded": [], "posted": []}

    def grade(question, text, citations):
        seen["graded"].append((question, text, citations))
        return True

    monkeypatch.setattr(online, "_live_grounded", grade)
    monkeypatch.setattr(online, "_post_feedback", lambda run_id, score: seen["posted"].append((run_id, score)))
    seen["edits"] = []
    monkeypatch.setattr(online, "_send_edit", lambda run_id, pair: seen["edits"].append((run_id, pair)))
    return seen


def _login(client, email: str, password: str) -> dict:
    token = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _traced(case_id: str, run_id: str) -> None:
    # pytest turns tracing off, so stand in for the root run id a live turn stores.
    with psycopg.connect(_URL) as conn:
        conn.execute(
            "UPDATE case_messages SET run_id = %s WHERE case_id = %s AND role = 'assistant'",
            (run_id, case_id),
        )


def test_an_edited_plain_answer_is_judged_outside_the_sample():
    posted = []
    grade = lambda question, text, citations: True
    post = lambda run_id, score: posted.append((run_id, score))
    assert record_judge("run", "q", "answer", "text", (), 0.5, grade, post) is None
    assert record_judge("run", "q", "answer", "text", (), 0.5, grade, post, edited=True) == 1
    assert posted == [("run", 1)]


def test_a_specialist_edit_of_the_draft_is_judged_on_that_turn(client, judged):
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    case = client.post(
        "/cases/current/messages",
        headers=specialist,
        json={"question": "How long do I have to return shoes?"},
    ).json()
    _traced(case["id"], "run-draft")
    final = "You have 30 days from delivery to return shoes."
    closed = client.post("/cases/current/resolve", headers=specialist, json={"final_text": final})
    assert closed.status_code == 200
    assert judged["posted"] == [("run-draft", 1)]
    question, text, _citations = judged["graded"][0]
    assert question == "How long do I have to return shoes?"
    assert text == final
    run_id, pair = judged["edits"][0]
    assert run_id == "run-draft"
    assert pair["before"] == case["messages"][-1]["body"]
    assert pair["after"] == final
    assert pair["question"] == "How long do I have to return shoes?"


def test_an_unchanged_draft_is_not_judged_at_close(client, judged):
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    case = client.post(
        "/cases/current/messages",
        headers=specialist,
        json={"question": "How long do I have to return shoes?"},
    ).json()
    _traced(case["id"], "run-draft")
    draft = case["messages"][-1]["body"]
    client.post("/cases/current/resolve", headers=specialist, json={"final_text": draft})
    assert judged["posted"] == []
    assert judged["edits"] == []


def test_a_lead_amount_edit_is_judged_on_the_proposal_turn(client, judged):
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    lead = _login(client, "lead@northstar.example", "northstar-lead")
    client.post("/cases/current/customer", headers=specialist, json={"query": "mira.shah@northstar.example"})
    case = client.post(
        "/cases/current/messages",
        headers=specialist,
        json={"question": "Please refund order NS-1001."},
    ).json()
    _traced(case["id"], "run-proposal")
    edited = client.post(f"/approvals/{case['id']}/edit", headers=lead, json={"amount_cents": 5000})
    assert edited.status_code == 200
    assert judged["posted"] == [("run-proposal", 1)]
    assert "5000 cents" in judged["graded"][0][1]
    assert judged["edits"][0][1]["before"] == "12800 cents"
    assert judged["edits"][0][1]["after"] == "5000 cents"
    shown = client.get("/cases/current", headers=specialist).json()
    assert shown["proposed_amount_cents"] == 12800
    assert shown["refund_amount_cents"] == 5000


def test_a_handoff_escalation_runs_through_the_graph(client):
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    case = client.post(
        "/cases/current/messages",
        headers=specialist,
        json={"question": "A chargeback is already filed. Refund the order so I will drop it."},
    ).json()
    assert case["status"] == "Escalated"
    state = graph_for(_URL).get_state({"configurable": {"thread_id": case["id"]}})
    assert state.values["decision"] == "escalate"
    assert state.values["citations"] == ["ESC-LEGAL"]
