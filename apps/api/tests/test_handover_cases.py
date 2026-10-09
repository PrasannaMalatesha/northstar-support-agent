"""Hand-over decisions measured like every other route (issue #145, R35, R39).

The labeled hand-over cases run through the customer chat with the eval's own target and evaluator.
Each customer chat turn names why it handed over, for its traced LangGraph root run. No LangSmith call.
"""

import langchain_core.tracers.langchain as langchain_tracers
import pytest

import northstar.agent_model as agent_model
from evals.experiments import chat_turns, code_scores, e2e_example
from evals.labeled import CASES, HANDOVER_CASES, PHOTO_CASES, SLICE2_CASES, SPANISH_CASES
from northstar import cases, graph, online
from northstar.graph import TurnTools, run_turn
from test_leave_message import OFF_TOPIC
from test_live_chat import LIVE, _avery, _chat, _lead, _say

PERSON = "I want to talk to a person."


def test_the_handover_cases_are_new_ids_with_known_offers():
    ids = [case["id"] for case in HANDOVER_CASES]
    others = {case["id"] for group in (CASES, SLICE2_CASES, SPANISH_CASES, PHOTO_CASES) for case in group}
    assert len(ids) == len(set(ids)) and not set(ids) & others
    assert {case["decision"] for case in HANDOVER_CASES} == {"talk_to_person", "leave_message", "none"}
    assert {case["live"] for case in HANDOVER_CASES} == {True, False}


@pytest.mark.parametrize(
    ("client", "case"),
    [({"live_agents_enabled": case["live"]}, case) for case in HANDOVER_CASES],
    indirect=["client"],
    ids=[case["id"] for case in HANDOVER_CASES],
)
def test_handover_case(client, case):
    example = e2e_example(case, "update-handover")
    outputs = chat_turns(client, example["inputs"])
    scores = {score["key"]: score["score"] for score in code_scores(example["inputs"], outputs, example["outputs"])}
    assert scores["label_match"] == 1, outputs
    assert scores["citation_valid"] == 1


@pytest.fixture()
def reasons(monkeypatch):
    """The hand-over reason of each turn, as run_turn reads it for a traced root run. pytest never traces."""
    seen = []

    def traced(question, tools, graph=None, thread_id=None, handoff=None):
        draft = run_turn(question, tools, graph=graph, thread_id=thread_id)
        seen.append(None if handoff is None else handoff(draft.decision))
        return draft

    monkeypatch.setattr(cases, "run_turn", traced)
    return seen


def test_each_chat_turn_names_its_handover_reason(client, reasons):
    chat = _chat(client)
    for question in OFF_TOPIC:
        _say(client, chat, question)
    assert reasons == ["none", "none", "three_failures"]
    # A fourth failed turn: the offer still stands after it.
    _say(client, chat, "What is your favorite color?")
    assert reasons[-1] == "three_failures"
    _say(client, chat, PERSON)
    assert reasons[-1] == "requested"
    _say(client, chat, "I will open a chargeback with my bank.")
    assert reasons[-1] == "escalated"


def test_a_desk_turn_records_no_handover(client, reasons):
    token = client.post("/auth/login", json={"email": "specialist@northstar.example", "password": "northstar-specialist"})
    headers = {"Authorization": f"Bearer {token.json()['access_token']}"}
    for question in (PERSON, "What is your favorite color?", "I will open a chargeback."):
        sent = client.post("/cases/current/messages", headers=headers, json={"question": question})
    # On the desk a specialist is the person: the words are a question for the handbook, not a hand-over.
    assert [m["decision"] for m in sent.json()["messages"] if m["role"] == "assistant"] == ["abstain", "abstain", "escalate"]
    assert reasons == [None, None, None]


def test_asking_for_a_person_offers_to_leave_a_message_and_the_packet_says_why(client):
    chat = _chat(client)
    reply = _say(client, chat, PERSON)["messages"][-1]["text"]
    assert reply == cases.PERSON_TEXT
    assert client.get("/chat/state", headers=chat).json() == {"offer": "leave_message", "live_enabled": False, "live": None}
    left = client.post("/chat/leave-message", headers=chat, json={"text": "Please call me about my coat."})
    assert left.status_code == 200, left.text
    [item] = client.get("/inbox", headers=_lead(client)).json()
    assert "The customer asked for a person." in item["handoff"]
    # The request is not a gap in the handbook.
    assert client.get("/gaps", headers=_lead(client)).json() == []


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_with_live_chat_on_asking_for_a_person_offers_one_and_a_turn_that_helps_withdraws_it(client):
    client.post("/presence", headers=_avery(client), json={"state": "available"})
    chat = _chat(client)
    assert _say(client, chat, PERSON)["messages"][-1]["text"] == cases.PERSON_TEXT_LIVE
    assert client.get("/chat/state", headers=chat).json()["offer"] == "talk_to_person"
    _say(client, chat, "How long may apparel and footwear be returned?")
    assert client.get("/chat/state", headers=chat).json()["offer"] is None
    _say(client, chat, "Can I speak with a human, please?")
    assert client.post("/chat/live", headers=chat).json() == {"live": {"status": "offered", "specialist": None}}
    # In the line, the offer is gone: a person is on the way.
    assert client.get("/chat/state", headers=chat).json()["offer"] is None


class Graph:
    """A finished turn, with no LangChain run inside it, so nothing is traced or sent."""

    def invoke(self, state, config, context):
        return {"decision": "abstain", "text": "No.", "citations": [], "match": {}, "steps": [], "followup": "No."}


def test_a_traced_turn_hands_its_handover_reason_to_the_upload(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    monkeypatch.setattr(agent_model, "_load_local_env", lambda: None)
    monkeypatch.setattr(graph, "_scrubbed_client", lambda: None)
    jobs = []
    monkeypatch.setattr(online, "background", lambda fn, *args: jobs.append((fn, args)))
    unused = TurnTools(refund=lambda _q: None, support=lambda _q: None)
    draft = run_turn("Tell me a joke.", unused, graph=Graph(), handoff=lambda decision: f"reason for {decision}")
    assert draft.run_id is not None
    assert jobs == [(graph._upload_then_judge, (draft.run_id, "Tell me a joke.", "abstain", "No.", [], "reason for abstain"))]
    jobs.clear()
    run_turn("Tell me a joke.", unused, graph=Graph())
    assert jobs[0][1][-1] is None  # no hand-over to record


def test_the_upload_posts_the_handover_reason_then_the_judge(monkeypatch):
    calls = []

    class Client:
        def flush(self):
            calls.append("upload")

    monkeypatch.setattr(langchain_tracers, "wait_for_all_tracers", lambda: None)
    monkeypatch.setattr(graph, "_scrubbed_client", Client)
    monkeypatch.setattr(online, "_post_feedback", lambda run_id, score, **fields: calls.append((run_id, score, fields)))
    monkeypatch.setattr(online, "record_judge", lambda *args: calls.append("judge"))
    graph._upload_then_judge("run-1", "I want a person.", "person_requested", "A specialist can join.", [], "requested")
    assert calls == ["upload", ("run-1", 1, {"key": "handoff_reason", "value": "requested"}), "judge"]
    calls.clear()
    graph._upload_then_judge("run-2", "Tell me a joke.", "abstain", "No.", [], None)
    assert calls == ["upload", "judge"]


def test_the_handover_score_is_one_for_a_handover_and_zero_for_none():
    posted = []
    post = lambda run_id, score, **fields: posted.append((run_id, score, fields["value"]))
    assert [online.record_handoff("run", reason, post) for reason in ("escalated", "none")] == [1, 0]
    assert posted == [("run", 1, "escalated"), ("run", 0, "none")]

