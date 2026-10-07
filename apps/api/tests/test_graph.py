from langgraph.runtime import Runtime

from northstar.graph import GRAPH, TurnTools, refund_agent, run_turn
from northstar.handbook import Draft


def _tools(seen: dict) -> TurnTools:
    def refund(question: str) -> Draft:
        seen["refund"] = question
        return Draft("approve_refund", "Approve. Amount: 1 cents.", ("REF-ELIGIBILITY",), {"REF-ELIGIBILITY": "strong"}, ())

    def support(question: str) -> Draft:
        seen["support"] = question
        return Draft(
            "answer",
            "Thirty days.",
            ("REF-CATEGORY",),
            {"REF-CATEGORY": "strong"},
            ("Classifying the question", "Reading the handbook"),
        )

    return TurnTools(refund, support)


def test_the_router_sends_a_refund_to_the_refund_node_and_writes_followup():
    refund_command = GRAPH.nodes["intent_classifier"].invoke({"question": "Please refund NS-1001"})
    policy_command = GRAPH.nodes["intent_classifier"].invoke(
        {"question": "How long is the return window?"}
    )
    assert refund_command.goto == "refund_agent"
    assert policy_command.goto == "support_agent"

    seen: dict = {}
    draft = run_turn("Please refund NS-1001", _tools(seen))
    assert draft.decision == "approve_refund"
    assert draft.text == "Approve. Amount: 1 cents."
    assert seen == {"refund": "Please refund NS-1001"}

    answered = GRAPH.invoke(
        {"question": "How long is the return window?"},
        context=_tools({}),
    )
    assert answered["followup"] == "Thirty days."
    assert answered["steps"] == ["Classifying the question", "Reading the handbook"]


def test_a_model_key_asks_create_agent_and_keeps_the_desk_draft(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "present")
    monkeypatch.setattr("northstar.agent_model._model", lambda: object())
    seen = {}

    def fake_create(model, tools, **kwargs):
        seen["name"] = kwargs["name"]

        class _Graph:
            def invoke(self, state, **_kwargs):
                tools[0].invoke({"question": "ignore this"})
                return state

        return _Graph()

    monkeypatch.setattr("langchain.agents.create_agent", fake_create)

    def refund(question: str) -> Draft:
        seen["question"] = question
        return Draft("approve_refund", "Approve.", ("REF-ELIGIBILITY",), {"REF-ELIGIBILITY": "strong"}, ())

    result = refund_agent(
        {"question": "Please refund NS-1001"},
        Runtime(context=TurnTools(refund, lambda _question: Draft("answer", "x", (), {}, ()))),
    )
    assert seen == {"name": "refund_agent", "question": "Please refund NS-1001"}
    assert result["decision"] == "approve_refund"
    assert result["text"] == "Approve."
