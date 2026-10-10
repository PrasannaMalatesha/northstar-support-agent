"""Escalations and repeated failures reach the line (issue #141, R35, R39).

With live chat on, an escalation in the customer chat joins the line ahead of requested chats when a
specialist is available and the wait is under the cap. Otherwise it goes to the escalations inbox as
before. Three failed turns offer "Talk to a person", and a customer the line turns away may leave a message.
"""

import northstar.cases as cases_module
import pytest
from northstar.cases import COME_BACK_TEXT, LINE_REFUSED_TEXT, OFFERED_TEXT, CaseStore
from test_leave_message import OFF_TOPIC
from test_live_chat import JON, LIVE, MIRA, _avery, _chat, _customers, _db, _lead, _say
from test_live_line import FEW, _busy, _history, _join, _status

CHARGEBACK = "I will open a chargeback with my bank."
FOLLOW_UP = "A specialist will follow up with you about this."
INBOX_STATUS = f"A specialist will follow up with you. {COME_BACK_TEXT}"


def _requests() -> list[tuple[str, str]]:
    with _db() as conn:
        return [(row["reason"], row["status"]) for row in conn.execute("SELECT reason, status FROM live_chat_requests ORDER BY queued_at, id")]


def _state(client, chat) -> dict:
    return client.get("/chat/state", headers=chat).json()


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_a_chat_escalation_joins_the_line_and_the_specialist_reads_the_handoff_and_the_conversation(client, monkeypatch):
    avery, lead = _avery(client), _lead(client)
    client.post("/presence", headers=avery, json={"state": "available"})
    chat = _chat(client)
    _say(client, chat, "How long may apparel and footwear be returned?")

    view = _say(client, chat, CHARGEBACK)
    assert view["messages"][-1] == {"role": "assistant", "text": FOLLOW_UP}
    assert view["status"] == OFFERED_TEXT
    assert _state(client, chat) == {"follow_up": None, "live_enabled": True, "live": {"status": "offered", "specialist": None}}
    assert _requests() == [("escalated", "offered")]
    # In the line, not in the inbox: one person works it.
    assert client.get("/inbox", headers=lead).json() == []

    [offer] = client.get("/live", headers=avery).json()["offers"]
    assert (offer["customer"], offer["reason"], offer["language"]) == ("Mira Shah", "escalated", "en")
    assert client.post(f"/live/{offer['id']}/accept", headers=avery).status_code == 200
    [held] = client.get("/live", headers=avery).json()["chats"]
    assert held["handoff"].startswith(f"Asked: {CHARGEBACK}")
    assert "(ESC-LEGAL)" in held["handoff"] and "Owner: legal" in held["handoff"]
    assert [m["role"] for m in held["messages"]] == ["user", "assistant", "user", "assistant"]
    assert held["messages"][2:] == [{"role": "user", "text": CHARGEBACK}, {"role": "assistant", "text": FOLLOW_UP}]
    # The customer never sees the packet.
    assert "Owner:" not in str(client.get("/chat", headers=chat).json())

    monkeypatch.setattr(CaseStore, "ask", lambda *args, **kwargs: pytest.fail("the agent took a turn"))
    _say(client, chat, "Are you there?")
    monkeypatch.undo()
    reply = {"text": "Hi Mira, I am Avery. Our payments team handles disputes. No refund is promised."}
    assert client.post(f"/live/{offer['id']}/messages", headers=avery, json=reply).status_code == 200
    assert client.post(f"/live/{offer['id']}/resolve", headers=avery).status_code == 200
    assert client.get(f"/cases/{held['case_id']}", headers=lead).json()["status"] == "Resolved"
    assert client.get("/inbox", headers=lead).json() == []


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_an_escalation_waits_ahead_of_requested_chats_and_the_agent_stays_quiet(client, clock, monkeypatch):
    customers = _customers(3)
    avery = _avery(client)
    _busy(client, clock, avery, customers[:2])
    requested = _join(client, clock, customers[2])
    clock.advance(seconds=1)
    chat = _chat(client)

    assert _say(client, chat, CHARGEBACK)["status"] == f"You are number 1 in line. {FEW}"
    assert _status(client, requested) == f"You are number 2 in line. {FEW}"
    assert _requests()[-2:] == [("requested", "waiting"), ("escalated", "waiting")]

    # The agent handed over: a message while the escalation waits is kept for the specialist, with no agent turn.
    monkeypatch.setattr(CaseStore, "ask", lambda *args, **kwargs: pytest.fail("the agent took a turn"))
    view = _say(client, chat, "Please refund order NS-1001.")
    monkeypatch.undo()
    assert view["messages"][-1] == {"role": "user", "text": "Please refund order NS-1001."}
    assert client.get("/approvals", headers=_lead(client)).json() == []

    # The next free slot goes to the escalation.
    offer = client.get("/live", headers=avery).json()["offers"][0]["id"]
    client.post(f"/live/{offer}/accept", headers=avery)
    client.post(f"/live/{offer}/resolve", headers=avery)
    assert _status(client, chat) == OFFERED_TEXT
    assert _status(client, requested) == f"You are number 1 in line. {FEW}"


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_a_waiting_customer_who_escalates_moves_up(client, clock):
    customers = _customers(3)
    _busy(client, clock, _avery(client), customers[:2])
    requested = _join(client, clock, customers[2])
    mira = _join(client, clock, MIRA)
    assert _status(client, mira) == f"You are number 2 in line. {FEW}"

    assert _say(client, mira, CHARGEBACK)["status"] == f"You are number 1 in line. {FEW}"
    assert _status(client, requested) == f"You are number 2 in line. {FEW}"
    assert _requests()[-2:] == [("requested", "waiting"), ("escalated", "waiting")]


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_with_nobody_available_the_escalation_goes_to_the_inbox(client):
    chat = _chat(client)
    view = _say(client, chat, CHARGEBACK)
    assert view["messages"][-1] == {"role": "assistant", "text": FOLLOW_UP}
    assert view["status"] == INBOX_STATUS
    # Not offered to leave a message: the escalation is already with the team.
    assert _state(client, chat) == {"follow_up": None, "live_enabled": True, "live": None}
    assert _requests() == [("escalated", "refused")]
    [item] = client.get("/inbox", headers=_lead(client)).json()
    assert item["source"] == "chat" and "(ESC-LEGAL)" in item["handoff"]


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_over_the_longest_wait_the_escalation_goes_to_the_inbox(client, clock):
    # One specialist with two slots and 30-minute chats: the first escalation waits about 15 minutes, the next 30.
    _history(clock, 30, 30, 30, 30, 30)
    customers = _customers(5)
    _busy(client, clock, _avery(client), customers[:2])
    # A requested chat waiting does not hold an escalation back.
    _join(client, clock, customers[2])

    clock.advance(seconds=1)
    first = _chat(client, customers[3])
    assert _say(client, first, CHARGEBACK)["status"] == "You are number 1 in line. The wait is about 10 to 22 minutes."
    clock.advance(seconds=1)
    second = _chat(client, customers[4])
    assert _say(client, second, CHARGEBACK)["status"] == INBOX_STATUS
    assert _state(client, second) == {"follow_up": None, "live_enabled": True, "live": None}
    assert _requests()[-2:] == [("escalated", "waiting"), ("escalated", "refused")]
    assert [item["customer"] for item in client.get("/inbox", headers=_lead(client)).json()] == ["Live Customer4"]


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_an_escalation_that_leaves_the_line_goes_to_the_inbox(client, clock):
    customers = _customers(3)
    fillers = _busy(client, clock, _avery(client), customers[:2])
    lead = _lead(client)

    # The customer leaves the line: the escalation does not go back to the agent.
    clock.advance(seconds=1)
    mira = _chat(client)
    _say(client, mira, CHARGEBACK)
    assert client.delete("/chat/live", headers=mira).json() == {"live": None}
    assert _status(client, mira) == INBOX_STATUS
    assert _state(client, mira) == {"follow_up": None, "live_enabled": True, "live": None}
    assert [item["customer"] for item in client.get("/inbox", headers=lead).json()] == ["Mira Shah"]

    # A chat that stops refreshing for 2 minutes leaves the line, and the escalation goes to the inbox too.
    clock.advance(seconds=1)
    other = _chat(client, customers[2])
    _say(client, other, CHARGEBACK)
    clock.advance(minutes=2)
    _status(client, fillers[0])
    assert _requests()[-1] == ("escalated", "abandoned")
    assert [item["customer"] for item in client.get("/inbox", headers=lead).json()] == ["Mira Shah", "Live Customer2"]
    # Back, the customer does not rejoin the line: a specialist follows up from the inbox.
    assert _status(client, other) == INBOX_STATUS
    assert _requests()[-1] == ("escalated", "abandoned")


@pytest.mark.parametrize("client", [{"live_chat_enabled": True, "offers_before_leave_message": 1}], indirect=True)
def test_an_escalation_no_specialist_accepts_goes_to_the_inbox(client, clock):
    avery, lead = _avery(client), _lead(client)
    client.post("/presence", headers=avery, json={"state": "available"})
    mira = _chat(client)
    _say(client, mira, CHARGEBACK)
    [offer] = client.get("/live", headers=avery).json()["offers"]
    assert client.post(f"/live/{offer['id']}/decline", headers=avery).status_code == 200
    assert _requests() == [("escalated", "unanswered")]
    assert _status(client, mira) == INBOX_STATUS
    # The escalation is with the team already, so there is no message to leave.
    assert _state(client, mira) == {"follow_up": None, "live_enabled": True, "live": None}
    assert [item["customer"] for item in client.get("/inbox", headers=lead).json()] == ["Mira Shah"]

    # An offer that expires is the same.
    clock.advance(seconds=1)
    jon = _chat(client, JON)
    _say(client, jon, CHARGEBACK)
    clock.advance(seconds=45)
    client.get("/live", headers=avery)
    assert _requests()[-1] == ("escalated", "unanswered")
    assert _status(client, jon) == INBOX_STATUS
    assert [item["customer"] for item in client.get("/inbox", headers=lead).json()] == ["Mira Shah", "Jon Hale"]


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_a_desk_escalation_does_not_join_the_line(client):
    avery = _avery(client)
    client.post("/presence", headers=avery, json={"state": "available"})
    desk = client.post("/cases/current/messages", headers=avery, json={"question": CHARGEBACK}).json()
    assert desk["status"] == "Escalated"
    assert _requests() == []


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_three_failed_turns_offer_a_person_and_a_turned_away_customer_may_leave_a_message(client):
    chat = _chat(client)
    for question in OFF_TOPIC:
        _say(client, chat, question)
    assert _state(client, chat) == {"follow_up": "talk_to_person", "live_enabled": True, "live": None}
    assert client.post("/chat/leave-message", headers=chat, json={"text": "Please call me."}).status_code == 409

    # Nobody is available: the line turns the customer away, and the offer becomes leaving a message.
    assert client.post("/chat/live", headers=chat).json() == {"live": None}
    assert _state(client, chat)["follow_up"] == "leave_message"
    assert _status(client, chat) == LINE_REFUSED_TEXT
    left = client.post("/chat/leave-message", headers=chat, json={"text": "Please call me about my coat."})
    assert left.status_code == 200
    assert left.json()["status"] == INBOX_STATUS
    [item] = client.get("/inbox", headers=_lead(client)).json()
    assert "Please call me about my coat." in item["handoff"]


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_three_failed_turns_then_talk_to_a_person_joins_the_line(client):
    avery = _avery(client)
    client.post("/presence", headers=avery, json={"state": "available"})
    chat = _chat(client)
    for question in OFF_TOPIC:
        _say(client, chat, question)
    assert _state(client, chat)["follow_up"] == "talk_to_person"
    assert client.post("/chat/live", headers=chat).json() == {"live": {"status": "offered", "specialist": None}}
    assert _state(client, chat)["follow_up"] is None
    assert _requests() == [("requested", "offered")]


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_an_escalation_in_spanish_is_offered_with_its_language(client, monkeypatch):
    avery = _avery(client)
    client.post("/presence", headers=avery, json={"state": "available"})
    chat = _chat(client)
    spanish = "Abriré un contracargo con mi banco."
    # pytest makes no model call, so the translation is set here. The escalating message is not saved yet
    # when its request joins the line, and the offer still has its language.
    monkeypatch.setattr(cases_module, "to_english", lambda text: CHARGEBACK if text == spanish else text)
    _say(client, chat, spanish)
    [offer] = client.get("/live", headers=avery).json()["offers"]
    assert (offer["reason"], offer["language"]) == ("escalated", "es")
