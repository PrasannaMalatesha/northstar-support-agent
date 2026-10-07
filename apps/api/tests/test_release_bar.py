import os
import time
from datetime import datetime, timezone

import psycopg
from evals.labeled import CASES, matches, registry_ids
from evals.release_bar import gates, online_checks
from northstar.handbook import answer

from tests.test_labeled_set import _clear_cases, _fresh, _login

_TEST_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://northstar:northstar@localhost:5433/northstar_test",
)
_START = datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc)


def _row(**over) -> dict:
    row = {
        "passed": True,
        "decision": "answer",
        "wanted": "answer",
        "citations": ["REF-CATEGORY"],
        "bad_citation": False,
        "ticket": False,
        "seconds": 0.01,
    }
    row.update(over)
    return row


def test_a_miss_on_each_gate_is_reported():
    assert gates([_row(passed=False) for _ in range(3)] + [_row() for _ in range(7)]) == ["action correct"]
    assert "ticket without approval" in gates([_row(ticket=True)])
    assert "invalid citation" in gates([_row(bad_citation=True)])
    assert "abstain" in gates([_row(wanted="abstain", decision="answer")])
    assert "latency" in gates([_row(seconds=11)])
    assert "token cap" in gates([_row(citations=["A", "B", "C", "D", "E"])])
    assert gates([_row()]) == []


def test_online_checks_always_cover_safety_and_sample_judges():
    assert online_checks("answer", False, 0.5) == {"safety": True, "judge": False}
    assert online_checks("answer", False, 0.05)["judge"] is True
    assert online_checks("abstain", False, 0.5)["judge"] is True
    assert online_checks("escalate", False, 0.5)["judge"] is True
    assert online_checks("answer", True, 0.5)["judge"] is True


def test_the_held_out_set_meets_the_release_bar(client, clock):
    legal = registry_ids()
    rows = []
    for case in CASES:
        if case["split"] != "test" or case["channel"] != "handbook":
            continue
        started = time.perf_counter()
        draft = answer(case["question"])
        citations = list(draft.citations)
        rows.append(
            {
                "passed": matches(case, draft.decision, citations, draft.text),
                "decision": draft.decision,
                "wanted": case["decision"],
                "citations": citations,
                "bad_citation": any(section not in legal for section in citations),
                "ticket": False,
                "seconds": time.perf_counter() - started,
            }
        )

    _clear_cases()
    clock.moment = _START
    headers = _login(client, "specialist@northstar.example", "northstar-specialist")
    lead_headers = _login(client, "lead@northstar.example", "northstar-lead")
    for case in CASES:
        if case["split"] != "test" or case["channel"] != "desk":
            continue
        if case.get("advance_days"):
            clock.advance(days=case["advance_days"])
            headers = _login(client, "specialist@northstar.example", "northstar-specialist")
            lead_headers = _login(client, "lead@northstar.example", "northstar-lead")
        _fresh(client, headers, lead_headers, clock)
        if case["customer"]:
            client.post("/cases/current/customer", headers=headers, json={"query": case["customer"]})
        started = time.perf_counter()
        response = client.post(
            "/cases/current/messages",
            headers=headers,
            json={"question": case["question"]},
        )
        seconds = time.perf_counter() - started
        assert response.status_code == 200, response.text
        body = response.json()
        draft = body["messages"][-1]
        citations = list(draft["citations"])
        ok = (
            draft["decision"] == case["decision"]
            and all(section in citations for section in case["sections"])
            and body["status"] == case["status"]
            and body["ticket_id"] is None
        )
        rows.append(
            {
                "passed": ok,
                "decision": draft["decision"],
                "wanted": case["decision"],
                "citations": citations,
                "bad_citation": any(section not in legal for section in citations),
                "ticket": body["ticket_id"] is not None,
                "seconds": seconds,
            }
        )

    assert gates(rows) == [], gates(rows)
    with psycopg.connect(_TEST_URL) as conn:
        count = conn.execute("SELECT count(*) FROM tickets").fetchone()[0]
    assert count == 0
