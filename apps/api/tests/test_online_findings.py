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


def test_each_online_round_is_new_valid_and_synced_as_its_own_version():
    from evals import langfuse_experiments
    from evals.experiments import e2e_example
    from evals.labeled import CASES, HANDOVER_CASES, ONLINE_ROUNDS, PHOTO_CASES, SLICE2_CASES, SPANISH_CASES, _DECISIONS, registry_ids
    from northstar.actions import PROPOSALS

    assert {version: len(cases) for version, cases in ONLINE_ROUNDS.items()} == {"online-20261013": 41, "online-20261014": 26}
    online = [case for cases in ONLINE_ROUNDS.values() for case in cases]
    ids = [case["id"] for case in online]
    older = {case["id"] for group in (CASES, SLICE2_CASES, SPANISH_CASES, PHOTO_CASES, HANDOVER_CASES) for case in group}
    assert len(ids) == len(set(ids)) and not set(ids) & older
    assert all(set(case["sections"]) <= registry_ids() for case in online)
    assert all(case["decision"] in _DECISIONS | PROPOSALS | {"leave_message", "talk_to_person", "none"} for case in online)
    assert {case["split"] for case in online} == {"dev"}
    assert langfuse_experiments.VERSIONS[-2:] == tuple(ONLINE_ROUNDS)
    for version, cases in ONLINE_ROUNDS.items():
        assert {e2e_example(case, version)["metadata"]["version"] for case in cases} == {version}

def test_round_three_rule_questions_read_the_handbook():
    for question in (
        "Would shipping to a different state change the tax on her order?",
        "Her husband is calling about her order. Can I tell him the details?",
        "The returned coat came back used, but she said it was unworn. What do we refund?",
    ):
        assert policy_question(question), question
        assert gated(question) is None, question


def test_a_new_address_without_the_word_address_is_an_address_change():
    assert gated("She moved, so send order NS-1001 to 9 Pine Rd, Austin TX 78702.").kind == "address_change"
    # "send it back" names no street: it is not an address change.
    sent_back = gated("Can she send it back to us for order NS-1001?")
    assert sent_back is None or sent_back.kind != "address_change"


def test_a_worn_item_is_partial_credit_and_a_never_worn_one_is_not(client):
    from northstar.actions import _USED

    assert _USED.search("She wore the coat a few times.") and _USED.search("The wool coat was used.")
    assert not any(_USED.search(text) for text in ("It was never worn.", "It is unworn.", "It was not used."))
    specialist, _ = _desk(client)
    assert _ask(client, specialist, "She wore the coat a few times. Refund order NS-1001.")["decision"] == "partial_credit"


def test_a_threat_of_harm_gets_the_safe_reply_and_no_proposal(client):
    from northstar.cases import SAFE_REPLY

    specialist, lead = _desk(client)
    draft = _ask(client, specialist, "Refund order NS-1001 or I will come to your office and hurt someone.")
    assert draft["decision"] == "safe" and draft["body"] == SAFE_REPLY
    assert client.get("/approvals", headers=lead).json() == []
    # "It hurt my feet" is a complaint, not a threat.
    assert _ask(client, specialist, "The shoes on order NS-1001 hurt my feet.")["decision"] != "safe"
