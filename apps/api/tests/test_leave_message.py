"""Repeated failures offer a follow-up (R35): after failed turns in a row, the chat offers to leave a message.

A left message becomes an escalated chat case in the escalations inbox (R38), with a handoff that stands alone.
"""

import pytest
from northstar.cases import COME_BACK_TEXT
from northstar.graph import LOOKUP_FAILED_TEXT
from northstar.handbook import Draft

MIRA = {"order_id": "NS-1001", "email": "mira.shah@northstar.example"}
OFF_TOPIC = ("What is your favorite color?", "Tell me a joke.", "Who won the game last night?")
HELPS = "How long may apparel and footwear be returned?"
LEFT = "Your message is with our team. A specialist will reply in this chat."


def _chat(client) -> dict:
    started = client.post("/chat/start", json=MIRA)
    assert started.status_code == 200, started.text
    return {"Authorization": f"Bearer {started.json()['chat_token']}"}


def _say(client, chat, question: str) -> dict:
    sent = client.post("/chat/messages", headers=chat, json={"question": question})
    assert sent.status_code == 200, sent.text
    return sent.json()


def _offer(client, chat):
    state = client.get("/chat/state", headers=chat)
    assert state.status_code == 200, state.text
    return state.json()["offer"]


def _staff(client, email, password) -> dict:
    token = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _failed_three_times(client) -> dict:
    chat = _chat(client)
    for question in OFF_TOPIC:
        _say(client, chat, question)
    return chat


def test_three_failed_turns_in_a_row_offer_to_leave_a_message(client):
    chat = _chat(client)
    assert client.get("/chat/state", headers=chat).json() == {"offer": None, "live_enabled": False, "live": None}
    for question in OFF_TOPIC[:2]:
        assert _say(client, chat, question)["messages"][-1]["text"].startswith("No handbook section covers that.")
        assert _offer(client, chat) is None
    _say(client, chat, OFF_TOPIC[2])
    assert client.get("/chat/state", headers=chat).json() == {"offer": "leave_message", "live_enabled": False, "live": None}
    # The chat view keeps its shape. The offer is only in /chat/state.
    assert set(client.get("/chat", headers=chat).json()) == {"status", "messages"}


def test_a_clarification_and_a_failed_lookup_count_as_failed_turns(client, monkeypatch):
    chat = _chat(client)
    _say(client, chat, "What is your favorite color?")
    assert _say(client, chat, "Please refund my order.")["messages"][-1]["text"].startswith("Which order id?")
    monkeypatch.setattr("northstar.cases.handbook_reply", lambda _q: Draft("lookup_failed", LOOKUP_FAILED_TEXT, (), {}, ()))
    _say(client, chat, "Tell me a joke.")
    assert _offer(client, chat) == "leave_message"


def test_a_turn_that_helps_resets_the_count(client):
    chat = _chat(client)
    _say(client, chat, OFF_TOPIC[0])
    _say(client, chat, OFF_TOPIC[1])
    assert "REF-CATEGORY" in _say(client, chat, HELPS)["messages"][-1]["text"]
    _say(client, chat, OFF_TOPIC[0])
    _say(client, chat, OFF_TOPIC[1])
    assert _offer(client, chat) is None
    _say(client, chat, OFF_TOPIC[2])
    assert _offer(client, chat) == "leave_message"
    # A turn that helps after the offer withdraws it.
    _say(client, chat, HELPS)
    assert _offer(client, chat) is None


@pytest.mark.parametrize("client", [{"failed_turns_before_offer": 2, "live_agents_enabled": True}], indirect=True)
def test_the_count_and_the_live_chat_switch_are_settings(client):
    chat = _chat(client)
    _say(client, chat, OFF_TOPIC[0])
    assert _offer(client, chat) is None
    _say(client, chat, OFF_TOPIC[1])
    assert client.get("/chat/state", headers=chat).json() == {"offer": "leave_message", "live_enabled": True, "live": None}


def test_a_message_is_left_only_while_the_offer_stands(client):
    chat = _chat(client)
    _say(client, chat, OFF_TOPIC[0])
    refused = client.post("/chat/leave-message", headers=chat, json={"text": "Please call me."})
    assert refused.status_code == 409
    assert client.post("/chat/leave-message", json={"text": "Please call me."}).status_code == 401
    specialist = _staff(client, "specialist@northstar.example", "northstar-specialist")
    assert client.post("/chat/leave-message", headers=specialist, json={"text": "Please call me."}).status_code == 401
    assert client.get("/chat/state", headers=specialist).status_code == 401


def test_a_left_message_is_screened_and_becomes_an_escalated_case_in_the_inbox(client):
    chat = _failed_three_times(client)
    assert client.post("/chat/leave-message", headers=chat, json={"text": "   "}).status_code == 422

    text = "My order NS-1001 is fine, I just need a person. Call me on 512-555-0199 or mira.home@example.com."
    left = client.post("/chat/leave-message", headers=chat, json={"text": text})
    assert left.status_code == 200, left.text
    view = left.json()
    assert set(view) == {"status", "messages"}
    assert view["messages"][-2] == {
        "role": "user",
        "text": "My order NS-1001 is fine, I just need a person. Call me on [phone] or [email].",
    }
    assert view["messages"][-1] == {"role": "assistant", "text": LEFT}
    assert view["status"] == f"A specialist will follow up with you. {COME_BACK_TEXT}"
    # The offer ends with the left message, and a second one is refused.
    assert _offer(client, chat) is None
    assert client.post("/chat/leave-message", headers=chat, json={"text": "Again."}).status_code == 409

    lead = _staff(client, "lead@northstar.example", "northstar-lead")
    [item] = client.get("/inbox", headers=lead).json()
    assert (item["source"], item["customer"], item["assigned_to"]) == ("chat", "Mira Shah", None)
    handoff = item["handoff"]
    assert handoff.startswith("Asked: My order NS-1001 is fine, I just need a person. Call me on [phone] or [email].")
    assert "Order: NS-1001" in handoff and "(ESC-WHEN)" in handoff and "Owner: specialist" in handoff
    assert "Tried: abstain; abstain; abstain" in handoff
    # The packet stands alone: the questions and replies that did not help.
    recent = handoff.split("Recent turns:\n", 1)[1].splitlines()
    assert recent[0::2] == [f"Customer: {question}" for question in OFF_TOPIC]
    assert all(line.startswith("Agent: No handbook section covers that.") for line in recent[1::2])
    assert "0199" not in handoff and "mira.home" not in handoff
    assert client.get(f"/cases/{item['case_id']}", headers=lead).json()["status"] == "Escalated"


def test_a_specialist_picks_up_the_left_message_and_the_reply_reaches_the_chat(client, clock):
    chat = _failed_three_times(client)
    client.post("/chat/leave-message", headers=chat, json={"text": "I need help choosing a gift."})
    specialist = _staff(client, "specialist@northstar.example", "northstar-specialist")
    [item] = client.get("/inbox", headers=specialist).json()
    assert client.post(f"/inbox/{item['case_id']}/pick-up", headers=specialist).status_code == 200
    reply = {"text": "Hi Mira, the wool coat is a popular gift. Sizes S to L are in stock."}
    assert client.post(f"/inbox/{item['case_id']}/reply", headers=specialist, json=reply).status_code == 200

    view = client.get("/chat", headers=chat).json()
    assert view["messages"][-2:] == [
        {"role": "assistant", "text": LEFT},
        {"role": "specialist", "name": "Avery", "text": reply["text"]},
    ]
    # Writing again starts a new chat case, with a fresh count and no offer.
    clock.advance(minutes=5)
    _say(client, chat, OFF_TOPIC[0])
    assert _offer(client, chat) is None
    assert client.get("/chat", headers=chat).json()["messages"][-1]["text"].startswith("No handbook section covers that.")


def test_a_left_message_in_spanish_is_confirmed_in_spanish(client):
    chat = _failed_three_times(client)
    view = client.post("/chat/leave-message", headers=chat, json={"text": "Hola, necesito hablar con una persona, por favor."}).json()
    assert view["messages"][-1]["text"] == "Su mensaje está con nuestro equipo. Un especialista responderá en este chat."
