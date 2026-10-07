from northstar.graph import GRAPH, TurnTools, run_turn
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
