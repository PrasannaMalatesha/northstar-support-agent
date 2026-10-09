"""Money actions in a live chat (issue #143, R45): the lead's approval gate holds.

The specialist raises the action through the agent's own turn, as themselves. A lead approves it.
"""

import uuid

import psycopg
import pytest
from conftest import TEST_URL
from northstar import cases as cases_module
from northstar.cases import CaseStore, ProposerCannotApprove
from northstar.identity.service import staff_id_for
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

LIVE = [{"live_agents_enabled": True}]
MIRA = {"order_id": "NS-1001", "email": "mira.shah@northstar.example"}
WAITING = "A person on our team is reviewing your request. Nothing is approved yet."


def _staff(client, email, password) -> dict:
    token = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _avery(client) -> dict:
    return _staff(client, "specialist@northstar.example", "northstar-specialist")


def _lead(client) -> dict:
    return _staff(client, "lead@northstar.example", "northstar-lead")


def _chat(client) -> dict:
    return {"Authorization": f"Bearer {client.post('/chat/start', json=MIRA).json()['chat_token']}"}


def _say(client, chat, question: str) -> dict:
    sent = client.post("/chat/messages", headers=chat, json={"question": question})
    assert sent.status_code == 200, sent.text
    return sent.json()


def _accepted(client, chat, specialist) -> str:
    assert client.post("/chat/live", headers=chat).status_code == 200
    client.post("/presence", headers=specialist, json={"state": "available"})
    offer = client.get("/live", headers=specialist).json()["offers"][0]["id"]
    assert client.post(f"/live/{offer}/accept", headers=specialist).status_code == 200
    return offer


def _act(client, specialist, offer, text: str):
    return client.post(f"/live/{offer}/actions", headers=specialist, json={"text": text})


def _held(client, specialist) -> dict:
    [chat] = client.get("/live", headers=specialist).json()["chats"]
    return chat


def test_with_the_setting_off_no_live_action_route_exists(client):
    assert _act(client, _avery(client), uuid.uuid4(), "Please refund order NS-1001.").status_code == 404


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_a_refund_raised_in_a_live_chat_waits_for_a_lead_and_the_specialist_cannot_approve_it(client, clock):
    chat, avery, lead = _chat(client), _avery(client), _lead(client)
    offer = _accepted(client, chat, avery)

    # Only the specialist who holds the live chat raises an action in it.
    assert _act(client, lead, offer, "Please refund order NS-1001.").status_code == 403
    assert _act(client, avery, uuid.uuid4(), "Please refund order NS-1001.").status_code == 403
    assert _act(client, avery, offer, "   ").status_code == 422

    assert _act(client, avery, offer, "Please refund order NS-1001.").status_code == 200
    [row] = client.get("/approvals", headers=lead).json()
    assert (row["order_id"], row["action"], row["amount_cents"]) == ("NS-1001", "approve_refund", 12800)
    assert row["citations"] == ["REF-ELIGIBILITY", "REF-CATEGORY"]
    case_id = uuid.UUID(row["case_id"])
    with psycopg.connect(TEST_URL, row_factory=dict_row) as conn:
        proposed_by = conn.execute("SELECT proposed_by FROM cases WHERE id = %s", (case_id,)).fetchone()["proposed_by"]
    assert proposed_by == staff_id_for("specialist@northstar.example")

    # The specialist cannot approve it: not through the API, and not as the proposer.
    assert client.post(f"/approvals/{case_id}/approve", headers=avery).status_code == 403
    with ConnectionPool(TEST_URL, min_size=1, max_size=1, kwargs={"row_factory": dict_row}) as pool:
        with pytest.raises(ProposerCannotApprove):
            CaseStore(pool, clock, live_chats=True).approve(proposed_by, case_id)

    # The customer sees that nothing is approved yet, and no ask, amount, or rule.
    view = client.get("/chat", headers=chat).json()
    assert view == {"status": WAITING, "messages": []}

    # The specialist sees their action and the desk's reply, and what the customer's status says.
    held = _held(client, avery)
    assert held["messages"] == [
        {"role": "action", "text": "Please refund order NS-1001."},
        {"role": "desk", "text": "Approve. Amount: 12800 cents. (REF-ELIGIBILITY, REF-CATEGORY)"},
    ]
    assert held["status"] == WAITING and held["spanish"] is False

    # While the proposal waits, the two keep talking. The agent stays quiet.
    _say(client, chat, "Thanks. I will wait here.")
    assert client.post(f"/live/{offer}/messages", headers=avery, json={"text": "A lead is looking at it now."}).status_code == 200
    assert [m["text"] for m in client.get("/chat", headers=chat).json()["messages"]] == [
        "Thanks. I will wait here.",
        "A lead is looking at it now.",
    ]

    # One proposal at a time, and the live chat does not end before the lead decides.
    assert _act(client, avery, offer, "Cancel order NS-1004.").status_code == 409
    assert client.post(f"/live/{offer}/resolve", headers=avery).status_code == 409
    assert client.post(f"/live/{offer}/escalate", headers=avery, json={"note": "Over to payments."}).status_code == 409
    assert [item["case_id"] for item in client.get("/approvals", headers=lead).json()] == [str(case_id)]

    ticket = client.post(f"/approvals/{case_id}/approve", headers=lead).json()["ticket_id"]
    approved = f"Our team approved your request. Reference {ticket}."
    assert client.get("/chat", headers=chat).json()["status"] == approved
    assert _held(client, avery)["status"] == approved

    # The duplicate guard holds for the specialist too: no second refund on the order.
    assert _act(client, avery, offer, "Please refund order NS-1001.").status_code == 200
    assert "already has a refund ticket" in _held(client, avery)["messages"][-1]["text"]
    assert client.get("/approvals", headers=lead).json() == []
    assert client.post(f"/live/{offer}/resolve", headers=avery).status_code == 200


@pytest.mark.parametrize("client", [{"live_agents_enabled": True, "request_limit": 1}], indirect=True)
def test_a_live_action_counts_against_the_specialists_own_request_limit(client):
    chat, avery = _chat(client), _avery(client)
    offer = _accepted(client, chat, avery)
    assert _act(client, avery, offer, "Cancel order NS-1001.").status_code == 200
    assert _act(client, avery, offer, "Please refund order NS-1001.").status_code == 200
    action, refused, _, limited = _held(client, avery)["messages"]
    assert action == {"role": "action", "text": "Cancel order NS-1001."}
    assert "cannot be cancelled" in refused["text"]
    assert limited == {"role": "desk", "text": cases_module.REQUEST_LIMIT_TEXT}
    assert client.get("/approvals", headers=_lead(client)).json() == []
    assert client.get("/chat", headers=chat).json() == {"status": "", "messages": []}


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_a_spanish_customer_gets_the_label_and_the_specialists_own_words(client, monkeypatch):
    chat, avery = _chat(client), _avery(client)
    offer = _accepted(client, chat, avery)
    assert _held(client, avery)["spanish"] is False

    # A person's words are never machine-translated, in either direction.
    def translated(*_args):
        pytest.fail("a person's words were machine-translated")

    monkeypatch.setattr(cases_module, "to_english", translated)
    monkeypatch.setattr(cases_module, "to_spanish", translated)
    _say(client, chat, "Hola, ¿dónde está mi pedido NS-1009?")
    assert _held(client, avery)["spanish"] is True
    for text in ("Hola Mira, soy Avery. Reviso su pedido ahora.", "I will also check with the carrier."):
        assert client.post(f"/live/{offer}/messages", headers=avery, json={"text": text}).status_code == 200
    assert client.get("/chat", headers=chat).json()["messages"] == [
        {"role": "user", "text": "Hola, ¿dónde está mi pedido NS-1009?"},
        {"role": "specialist", "name": "Avery", "text": "Hola Mira, soy Avery. Reviso su pedido ahora."},
        {"role": "specialist", "name": "Avery", "text": "I will also check with the carrier."},
    ]

    # The label follows the customer's latest message.
    _say(client, chat, "Thank you, that helps.")
    assert _held(client, avery)["spanish"] is False
