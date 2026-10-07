import os

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver

from northstar.graph import TurnTools, _compile, run_turn
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
    first = run_turn(
        "Please refund NS-1001",
        TurnTools(refund, support),
        graph=graph_for(_URL),
        thread_id=thread,
    )
    with PostgresSaver.from_conn_string(_URL) as saver:
        state = _compile(saver).get_state({"configurable": {"thread_id": thread}})
    assert state.values["followup"] == first.text
    assert state.values["followup"] == "Approve."
