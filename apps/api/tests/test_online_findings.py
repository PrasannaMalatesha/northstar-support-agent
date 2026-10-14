"""Fixes from the online evaluation run of 2026-10-13: live turns scored against labels written beforehand."""

from northstar.actions import gated, policy_question
from test_e2e_findings import _ask, _desk, _login


def test_new_ways_to_say_broken_lost_and_refund_reach_their_action():
    assert gated("The speaker from order NS-1007 died after two months.").kind == "warranty_claim"
    assert gated("Order NS-1009 still has not shown up.").kind == "shipment"
    assert gated("It never showed up, order NS-1009.").kind == "shipment"
    assert gated("I'd like my money back for NS-1003.").kind == "refund"


def test_a_staff_question_about_the_rule_reads_the_handbook():
    for question in (
        "The package shows delivered but the customer says it never came. What is the rule?",
        "Under warranty, do we repair, replace, or refund?",
        "The customer wants store credit instead of a refund to her card. Can we do that?",
        "Part of her order was missing from the box. What is the rule?",
    ):
        assert policy_question(question), question
        assert gated(question) is None, question


def test_a_request_with_an_order_or_from_a_customer_still_acts():
    # An order id makes it a request, whatever the question words.
    assert not policy_question("She changed her mind about the kettle, order NS-1004. Can we cancel it?")
    assert gated("She changed her mind about the kettle, order NS-1004. Can we cancel it?").kind == "cancel"
    # A customer's own request says "you", not "we": it still asks which order.
    assert not policy_question("My lamp broke. Can you help?")
    assert gated("My lamp broke. Can you help?").kind == "warranty_claim"


def test_a_rule_question_about_her_order_is_not_a_request_for_a_customer(client):
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    draft = _ask(client, specialist, "Part of her order was missing from the box. What is the rule?")
    assert draft["decision"] != "unbound"
    # Asking about one particular order still needs a customer first.
    assert _ask(client, specialist, "Where is her order?")["decision"] == "unbound"


def test_a_bound_customer_s_order_reaches_the_new_phrases(client):
    specialist, _ = _desk(client)
    assert _ask(client, specialist, "I'd like my money back for NS-1003.")["decision"] == "deny"


def test_the_online_cases_are_new_valid_and_synced_as_their_own_version():
    from evals import langfuse_experiments
    from evals.experiments import e2e_example
    from evals.labeled import CASES, HANDOVER_CASES, ONLINE_CASES, ONLINE_VERSION, PHOTO_CASES, SLICE2_CASES, SPANISH_CASES, _DECISIONS, registry_ids
    from northstar.actions import PROPOSALS

    ids = [case["id"] for case in ONLINE_CASES]
    older = {case["id"] for group in (CASES, SLICE2_CASES, SPANISH_CASES, PHOTO_CASES, HANDOVER_CASES) for case in group}
    assert len(ids) == len(set(ids)) == 41 and not set(ids) & older
    assert all(set(case["sections"]) <= registry_ids() for case in ONLINE_CASES)
    assert all(case["decision"] in _DECISIONS | PROPOSALS for case in ONLINE_CASES)
    assert {case["split"] for case in ONLINE_CASES} == {"dev"}
    assert langfuse_experiments.VERSIONS[-1] == ONLINE_VERSION
    assert {e2e_example(case, ONLINE_VERSION)["metadata"]["version"] for case in ONLINE_CASES} == {ONLINE_VERSION}
