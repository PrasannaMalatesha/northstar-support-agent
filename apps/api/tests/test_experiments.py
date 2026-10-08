"""The LangSmith dataset rows and evaluators, checked without a network call."""

from evals.experiments import (
    INTENT_CASES,
    _example_id,
    correct,
    e2e_example,
    intent_example,
    label_match,
    reference,
    route,
    status_correct,
    v0,
)
from evals.labeled import CASES, SLICE2_CASES


def test_every_case_becomes_one_example_with_a_stable_id():
    rows = [e2e_example(case, "slice1") for case in CASES] + [e2e_example(case, "slice2") for case in SLICE2_CASES]
    assert len({row["id"] for row in rows}) == len(CASES) + len(SLICE2_CASES)
    assert _example_id("apparel-window") == e2e_example(CASES[0], "slice1")["id"]
    assert {row["split"] for row in rows} == {"train_judge", "dev", "test"}


def test_the_judge_reference_is_the_gold_rule_or_the_abstain_text():
    by_id = {case["id"]: case for case in CASES}
    assert "30 days" in reference(by_id["apparel-window"])
    assert "(REF-CATEGORY)" in reference(by_id["apparel-window"])
    assert reference(by_id["favorite-color"]).startswith("No handbook section covers that.")
    assert e2e_example(by_id["chargeback"], "slice1")["outputs"]["response"] == ""


def test_label_match_needs_the_decision_the_sections_and_the_phrases():
    trap = e2e_example({case["id"]: case for case in CASES}["fourteen-day-trap"], "slice1")["outputs"]
    good = {"decision": "answer", "citations": ["REF-CATEGORY"], "response": "30 days from delivery."}
    assert label_match({}, good, trap)["score"] == 1
    assert label_match({}, {**good, "response": "14 days, then 30 days."}, trap)["score"] == 0
    assert label_match({}, {**good, "citations": []}, trap)["score"] == 0


def test_v0_is_scored_and_status_is_skipped_for_it():
    outputs = v0({"question": "What is your favorite color?"})
    assert outputs["decision"] == "abstain"
    assert status_correct({}, outputs, {"status": "Open"})["score"] is None


def test_the_router_rows_carry_hand_labels_and_the_latest_message_decides():
    assert len({case["id"] for case in INTENT_CASES}) == len(INTENT_CASES)
    for case in INTENT_CASES:
        example = intent_example(case)
        assert correct(example["inputs"], route(example["inputs"]), example["outputs"]), case["id"]
