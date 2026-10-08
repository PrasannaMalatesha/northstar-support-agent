import os

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver

from northstar.graph import TurnTools, _compile, resume_turn, run_turn
from northstar.handbook import Draft
from northstar.memory import graph_for

_ADMIN = os.environ.get(
    "DATABASE_URL",
    "postgresql://northstar:northstar@localhost:5433/northstar",
)
_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://northstar:northstar@localhost:5433/northstar_test",
)


def _ensure_test_database() -> None:
    with psycopg.connect(_ADMIN, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = 'northstar_test'"
        ).fetchone()
        if exists is None:
            conn.execute("CREATE DATABASE northstar_test")


def test_a_new_connection_still_has_the_thread():
    _ensure_test_database()
    def refund(_question: str) -> Draft:
        return Draft("approve_refund", "Approve.", ("REF-ELIGIBILITY",), {"REF-ELIGIBILITY": "strong"}, ())

    def support(_question: str) -> Draft:
        return Draft("answer", "Thirty days.", ("REF-CATEGORY",), {"REF-CATEGORY": "strong"}, ())

    thread = "thread-restart-check"
    graph = graph_for(_URL)
    first = run_turn(
        "Please refund NS-1001",
        TurnTools(refund, support),
        graph=graph,
        thread_id=thread,
    )
    config = {"configurable": {"thread_id": thread}}
    with PostgresSaver.from_conn_string(_URL) as saver:
        state = _compile(saver).get_state(config)
    assert state.next == ("compile_followup",)
    assert state.interrupts
    assert state.values["text"] == first.text == "Approve."
    resume_turn(graph, thread, "approve")
    with PostgresSaver.from_conn_string(_URL) as saver:
        done = _compile(saver).get_state(config)
    assert done.next == ()
    assert done.values["followup"] == "Approve."


def test_a_proposal_after_an_answer_shows_its_own_text():
    _ensure_test_database()

    def refund(_question: str) -> Draft:
        return Draft("approve_refund", "Approve. Amount: 12800 cents.", ("REF-ELIGIBILITY",), {"REF-ELIGIBILITY": "strong"}, ())

    def support(_question: str) -> Draft:
        return Draft("answer", "Thirty days.", ("REF-CATEGORY",), {"REF-CATEGORY": "strong"}, ())

    import uuid

    thread = f"thread-two-turns-{uuid.uuid4()}"
    graph = graph_for(_URL)
    first = run_turn("How long are returns?", TurnTools(refund, support), graph=graph, thread_id=thread)
    second = run_turn("Please refund NS-1001", TurnTools(refund, support), graph=graph, thread_id=thread)
    assert first.text == "Thirty days."
    assert second.decision == "approve_refund"
    assert second.text == "Approve. Amount: 12800 cents."
