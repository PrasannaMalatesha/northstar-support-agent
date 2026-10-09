import os
import time
from datetime import datetime, timezone

import psycopg
from evals.labeled import CASES, matches, registry_ids
from evals.release_bar import GATES, TOKEN_CAP, bad_citation, gates, missing_citation, online_checks, record
from northstar.online import record_judge, safety_code
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
        "tokens": 0,
    }
    row.update(over)
    return row


def test_a_miss_on_each_gate_is_reported():
    assert gates([_row(passed=False) for _ in range(3)] + [_row() for _ in range(7)]) == ["action correct"]
    assert "ticket without approval" in gates([_row(ticket=True)])
    assert "invalid citation" in gates([_row(bad_citation=True)])
    assert "missing citation" in gates([_row(decision="answer", citations=[])])
    assert gates([_row(decision="catalog", citations=[])]) == []
    assert "abstain" in gates([_row(wanted="abstain", decision="answer")])
    assert "latency" in gates([_row(seconds=11)])
    assert "token cap" in gates([_row(citations=["A", "B", "C", "D", "E"])])
    assert gates([_row()]) == []


def test_english_rows_keep_10_seconds_and_spanish_turns_have_their_own_20():
    english = [_row(seconds=9) for _ in range(19)] + [_row(seconds=30)]  # the slowest is past p95 of 20
    assert gates(english) == []
    assert gates([_row(seconds=10)]) == ["latency"]
    spanish = [_row(language="es", seconds=16) for _ in range(5)]
    assert gates([_row()] + spanish) == []
    assert gates([_row()] + spanish + [_row(language="es", seconds=21)]) == ["spanish latency"]
    # Spanish rows are dev cases: they never count toward action correct or the English latency.
    assert gates([_row()] + [_row(language="es", passed=False, seconds=19) for _ in range(9)]) == []
    assert gates([_row(language="es")]) == ["no rows"]


def test_the_token_cap_reads_the_tokens_each_turn_recorded():
    assert gates([_row(tokens=TOKEN_CAP)]) == []
    assert gates([_row(tokens=TOKEN_CAP + 1)]) == ["token cap"]
    assert gates([_row(), _row(language="es", tokens=TOKEN_CAP + 1)]) == ["token cap"]


def test_the_results_record_names_the_commit_and_every_gate():
    commit = "a" * 40
    rows = [_row(seconds=2.5, tokens=900), _row(language="es", seconds=15, tokens=2400)]
    passed = record(rows, commit)
    assert passed["commit"] == commit
    assert passed["rows"] == 2
    assert list(passed["gates"]) == list(GATES)
    assert all(passed["gates"].values())
    assert passed["measured"] == {"action_correct": 1.0, "p95_seconds_en": 2.5, "p95_seconds_es": 15, "max_tokens": 2400}
    failed = record(rows + [_row(seconds=12)], commit)
    assert [gate for gate, ok in failed["gates"].items() if not ok] == ["latency"]
    assert not any(record([], commit)["gates"].values())


def test_a_citation_must_be_in_the_registry_and_a_policy_answer_must_cite_one():
    legal = {"REF-CATEGORY"}
    assert bad_citation(["NOPE"], legal) is True
    assert bad_citation(["REF-CATEGORY"], legal) is False
    assert missing_citation("approve_refund", []) is True
    assert missing_citation("not_found", []) is False
    assert missing_citation("answer", ["REF-CATEGORY"]) is False


def test_a_live_trace_fails_safety_when_the_citation_is_unknown():
    namespace: dict = {}
    exec(safety_code({"REF-CATEGORY"}), namespace)
    perform = namespace["perform_eval"]
    assert perform({"outputs": {"decision": "answer", "citations": ["REF-CATEGORY"]}}) == {"safety": 1}
    assert perform({"outputs": {"decision": "answer", "citations": ["NOPE"]}}) == {"safety": 0}
    assert perform({"outputs": {"decision": "order", "citations": []}}) == {"safety": 1}
    assert perform({"error": "boom"}) == {"safety": 0}


def test_the_judge_runs_for_abstain_and_a_sample_and_skips_a_plain_answer():
    seen = []

    def grade(question, text, citations):
        seen.append(question)
        return True

    posted = []

    def post(run_id, score):
        posted.append((run_id, score))

    assert record_judge("run", "q", "answer", "text", (), 0.5, grade, post) is None
    assert seen == []
    assert record_judge("run", "q", "abstain", "text", (), 0.5, grade, post) == 1
    assert posted == [("run", 1)]
    assert online_checks("escalate", False, 0.5)["judge"] is True


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
                "bad_citation": bad_citation(citations, legal),
                "ticket": False,
                "seconds": time.perf_counter() - started,
                "tokens": 0,  # pytest calls no model
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
                "bad_citation": bad_citation(citations, legal),
                "ticket": body["ticket_id"] is not None,
                "seconds": seconds,
                "tokens": 0,  # pytest calls no model
            }
        )

    assert gates(rows) == [], gates(rows)
    with psycopg.connect(_TEST_URL) as conn:
        count = conn.execute("SELECT count(*) FROM tickets").fetchone()[0]
    assert count == 0
