from evals.trajectory import extra_step_count, trajectory_subsequence
from northstar.graph import TurnTools, turn_path
from northstar.handbook import Draft


def test_a_refund_path_scores_the_expected_steps_and_counts_a_ticket_call():
    def refund(_question: str) -> Draft:
        return Draft("approve_refund", "Approve.", ("REF-ELIGIBILITY",), {"REF-ELIGIBILITY": "strong"}, ())

    def support(_question: str) -> Draft:
        return Draft("answer", "Thirty days.", ("REF-CATEGORY",), {"REF-CATEGORY": "strong"}, ())

    path = turn_path("Please refund NS-1001", TurnTools(refund, support))
    reference = {"trajectory": ["intent_classifier", "refund_agent", "compile_followup"]}
    assert path == reference["trajectory"]
    assert trajectory_subsequence({"trajectory": path}, reference) == 1.0

    with_ticket = {"trajectory": [*path, "create_refund_ticket"]}
    assert trajectory_subsequence(with_ticket, reference) == 1.0
    assert extra_step_count(with_ticket, reference) == 1
    assert trajectory_subsequence({"trajectory": ["intent_classifier"]}, reference) is False
