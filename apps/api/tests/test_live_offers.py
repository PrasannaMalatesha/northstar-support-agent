"""Offers that move on (issue #139): an offer that is declined or not accepted in time goes to the next specialist.

Expiry is noticed whenever the line is read, with no scheduler (ADR 0001), so these tests move the clock and read.
"""

import pytest
from conftest import TEST_URL
from northstar.cases import LINE_REFUSED_TEXT
from northstar.identity.postgres import PostgresIdentityStore
from northstar.identity.service import hash_password, staff_id_for
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from test_live_chat import JON, _add_sam, _avery, _chat, _customers, _db, _lead, _live_events, _sam, _say, _staff

LIVE = [{"live_chat_enabled": True}]
AVERY = "specialist@northstar.example"
LEE = "lee.park@northstar.example"


def _add_lee() -> None:
    with ConnectionPool(TEST_URL, min_size=1, max_size=1, kwargs={"row_factory": dict_row}) as pool:
        PostgresIdentityStore(pool).upsert_staff(staff_id_for(LEE), LEE, "Lee Park", hash_password("northstar-third"), "specialist")


def _offers(client, staff) -> list[str]:
    return [offer["customer"] for offer in client.get("/live", headers=staff).json()["offers"]]


def _offer(client, staff) -> str:
    return client.get("/live", headers=staff).json()["offers"][0]["id"]


def _holder(client, specialists) -> dict:
    """The one specialist an offer is with. Each read is also that desk's check-in."""
    [holder] = [staff for staff in specialists if _offers(client, staff)]
    return holder


def _request() -> dict:
    with _db() as conn:
        return conn.execute("SELECT status, offers, missed_by FROM live_chat_requests").fetchone()


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_an_offer_not_accepted_within_45_seconds_goes_to_the_next_specialist(client, clock):
    _add_sam()
    chat, avery, sam = _chat(client), _avery(client), _sam(client)
    client.post("/presence", headers=avery, json={"state": "available"})
    client.post("/chat/live", headers=chat)
    offer = _offer(client, avery)
    client.post("/presence", headers=sam, json={"state": "available"})
    assert _offers(client, sam) == []

    clock.advance(seconds=44)
    assert _offers(client, avery) == ["Mira Shah"] and _offers(client, sam) == []

    # At 45 seconds the offer has expired. Reading the line moves it to Sam, and Avery can no longer take it.
    clock.advance(seconds=1)
    assert _offers(client, sam) == ["Mira Shah"]
    assert _offers(client, avery) == []
    assert client.post(f"/live/{offer}/accept", headers=avery).status_code == 403
    assert client.get("/chat/state", headers=chat).json()["live"] == {"status": "offered", "specialist": None}
    assert _request() == {"status": "offered", "offers": 2, "missed_by": [staff_id_for(AVERY)]}
    assert _live_events() == ["live_chat_requested", "live_chat_offered", "live_chat_expired", "live_chat_offered"]
    # One miss is not a run of misses: Avery stays available.
    assert client.get("/live", headers=avery).json()["state"] == "available"

    # Sam's offer has its own 45 seconds.
    clock.advance(seconds=44)
    assert client.post(f"/live/{offer}/accept", headers=sam).status_code == 200
    assert client.get("/chat/state", headers=chat).json()["live"] == {"status": "active", "specialist": "Sam"}


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_a_declined_offer_goes_to_the_next_specialist_and_never_back(client):
    _add_sam()
    chat, avery, sam, lead = _chat(client), _avery(client), _sam(client), _lead(client)
    client.post("/presence", headers=avery, json={"state": "available"})
    client.post("/chat/live", headers=chat)
    offer = _offer(client, avery)
    client.post("/presence", headers=sam, json={"state": "available"})

    assert client.post(f"/live/{offer}/decline", headers=sam).status_code == 403
    assert client.post(f"/live/{offer}/decline", headers=lead).status_code == 403
    assert client.post(f"/live/{offer}/decline", headers=avery).status_code == 200
    assert _offers(client, avery) == [] and _offers(client, sam) == ["Mira Shah"]
    assert client.post(f"/live/{offer}/decline", headers=avery).status_code == 403

    # Sam declines too. Both have free slots, but neither is offered it again: the customer waits for someone else.
    assert client.post(f"/live/{offer}/decline", headers=sam).status_code == 200
    assert _offers(client, avery) == [] and _offers(client, sam) == []
    assert client.get("/chat/state", headers=chat).json() == {
        "follow_up": None,
        "live_enabled": True,
        "live": {"status": "waiting", "specialist": None},
    }
    assert _request() == {"status": "waiting", "offers": 2, "missed_by": [staff_id_for(AVERY), staff_id_for("sam.ortiz@northstar.example")]}

    # Declining is not missing: both stay available, and the next customer reaches them.
    assert client.get("/live", headers=avery).json()["state"] == "available"
    assert client.get("/live", headers=sam).json()["state"] == "available"
    client.post("/chat/live", headers=_chat(client, JON))
    assert sorted(_offers(client, avery) + _offers(client, sam)) == ["Jon Hale"]
    assert _live_events().count("live_chat_declined") == 2


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_after_three_offers_the_customer_is_offered_to_leave_a_message_which_reaches_the_inbox(client, clock):
    _add_sam()
    _add_lee()
    chat = _chat(client)
    specialists = [_avery(client), _sam(client), _staff(client, LEE, "northstar-third")]
    _say(client, chat, "How long may apparel and footwear be returned?")
    for staff in specialists:
        client.post("/presence", headers=staff, json={"state": "available"})
    client.post("/chat/live", headers=chat)

    # First offer declined, second not accepted in time, third declined.
    first = _holder(client, specialists)
    client.post(f"/live/{_offer(client, first)}/decline", headers=first)
    second = _holder(client, specialists)
    clock.advance(seconds=45)
    third = _holder(client, specialists)
    assert len({first["Authorization"], second["Authorization"], third["Authorization"]}) == 3
    assert client.get("/chat/state", headers=chat).json()["follow_up"] is None
    client.post(f"/live/{_offer(client, third)}/decline", headers=third)

    # The request leaves the line, and the customer is offered to leave a message instead.
    assert all(_offers(client, staff) == [] for staff in specialists)
    assert _request()["status"] == "unanswered" and _request()["offers"] == 3
    assert client.get("/chat/state", headers=chat).json() == {"follow_up": "leave_message", "live_enabled": True, "live": None}
    assert client.get("/chat", headers=chat).json()["status"] == LINE_REFUSED_TEXT
    assert _live_events()[-2:] == ["live_chat_declined", "live_chat_unanswered"]

    left = client.post("/chat/leave-message", headers=chat, json={"text": "Please call me about my coat."})
    assert left.status_code == 200
    assert left.json()["status"].startswith("A specialist will follow up with you.")
    assert client.get("/chat/state", headers=chat).json()["follow_up"] is None
    [item] = client.get("/inbox", headers=_lead(client)).json()
    assert item["source"] == "chat" and item["customer"] == "Mira Shah"
    assert "Asked: Please call me about my coat." in item["handoff"]
    assert "no specialist accepted after 3 offers. The customer left this message for a specialist." in item["handoff"]


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_two_missed_offers_in_a_row_set_a_specialist_to_away(client, clock):
    chats = [_chat(client, body) for body in _customers(4)]
    avery = _avery(client)
    client.post("/presence", headers=avery, json={"state": "available"})

    # Missed, accepted, missed: not in a row, so Avery stays available.
    client.post("/chat/live", headers=chats[0])
    clock.advance(seconds=45)
    assert _offers(client, avery) == []
    client.post("/chat/live", headers=chats[1])
    assert client.post(f"/live/{_offer(client, avery)}/accept", headers=avery).status_code == 200
    client.post("/chat/live", headers=chats[2])
    clock.advance(seconds=45)
    live = client.get("/live", headers=avery).json()
    assert live["state"] == "available" and live["offers"] == [] and live["auto_away_at"] is None

    # A second miss in a row: Avery is set to away, sees when, and keeps the live chat already taken.
    client.post("/chat/live", headers=chats[3])
    assert _offers(client, avery) == ["Live Customer3"]
    clock.advance(seconds=45)
    live = client.get("/live", headers=avery).json()
    assert live["state"] == "away" and live["offers"] == []
    assert live["auto_away_at"] == clock.now().isoformat()
    assert [chat["customer"] for chat in live["chats"]] == ["Live Customer1"]
    assert _live_events().count("live_chat_auto_away") == 1

    # Choosing a state clears the note.
    client.post("/presence", headers=avery, json={"state": "available"})
    assert client.get("/live", headers=avery).json()["auto_away_at"] is None


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_a_desk_that_has_not_checked_in_for_60_seconds_gets_no_offers(client, clock):
    _add_sam()
    mira, jon, third = _chat(client), _chat(client, JON), _chat(client, _customers(1)[0])
    avery, sam = _avery(client), _sam(client)
    client.post("/presence", headers=avery, json={"state": "available"})
    client.post("/presence", headers=sam, json={"state": "available"})

    # Sam's desk checks in. Avery's has been quiet for 61 seconds, so Avery gets nothing, even with free slots.
    clock.advance(seconds=61)
    client.get("/live", headers=sam)
    client.post("/chat/live", headers=mira)
    clock.advance(seconds=1)
    client.post("/chat/live", headers=jon)
    clock.advance(seconds=1)
    client.post("/chat/live", headers=third)
    assert _offers(client, sam) == ["Mira Shah", "Jon Hale"]
    assert client.get("/chat/state", headers=third).json()["live"]["status"] == "waiting"

    # Avery's desk checks in again, and the waiting customer is offered to Avery at once.
    assert _offers(client, avery) == ["Live Customer0"]
