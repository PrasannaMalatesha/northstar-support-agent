"""The lead's view of the line, and its alerts (issue #144, R49).

Timers apply on read, so each step moves the test clock and reads. A specialist counts as available only while
their desk reads GET /live within the check-in window, as for offers (issue #139).
"""

import pytest
from conftest import TEST_URL
from northstar.identity.service import staff_id_for
from test_live_chat import JON, LIVE, MIRA, _add_sam, _avery, _chat, _customers, _db, _lead, _sam, _say, _staff
from test_live_line import _history
from test_live_offers import LEE, _add_lee, _holder, _offer

from northstar_api.settings import Settings

EMPTY = {"available": 0, "line_length": 0, "longest_wait_seconds": None, "average_chat_minutes": None, "alerts": []}


def _line(client, lead) -> dict:
    viewed = client.get("/line", headers=lead)
    assert viewed.status_code == 200, viewed.text
    return viewed.json()


def _numbers(client, lead) -> tuple:
    view = _line(client, lead)
    return view["available"], view["line_length"], view["longest_wait_seconds"]


def _accept(client, specialist) -> str:
    offer = _offer(client, specialist)
    assert client.post(f"/live/{offer}/accept", headers=specialist).status_code == 200
    return offer


def _case() -> str:
    """The case of the latest live chat request."""
    with _db() as conn:
        return str(conn.execute("SELECT case_id FROM live_chat_requests ORDER BY queued_at DESC, id DESC").fetchone()["case_id"])


def test_a_customer_is_flagged_after_2_minutes_without_a_reply_by_default():
    assert Settings(database_url=TEST_URL).quiet_specialist_minutes == 2


def test_with_the_setting_off_there_is_no_line_view(client):
    assert client.get("/line", headers=_lead(client)).status_code == 404


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_only_a_lead_reads_the_line(client):
    assert client.get("/line", headers=_avery(client)).status_code == 403
    assert client.get("/line").status_code == 401
    assert _line(client, _lead(client)) == EMPTY


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_the_lead_sees_specialists_available_the_line_and_the_longest_wait(client, clock):
    _add_sam()
    mira, jon, avery, sam, lead = _chat(client, MIRA), _chat(client, JON), _avery(client), _sam(client), _lead(client)
    client.post("/presence", headers=avery, json={"state": "available"})
    client.post("/presence", headers=sam, json={"state": "available"})
    assert _numbers(client, lead) == (2, 0, None)
    with _db() as conn:
        conn.execute("UPDATE specialist_availability SET capacity = 1")

    # Sam's desk stops checking in. After the window, Sam no longer counts, as for offers.
    clock.advance(seconds=61)
    client.get("/live", headers=avery)
    assert _numbers(client, lead) == (1, 0, None)

    # An offer not yet accepted is still in the line.
    client.post("/chat/live", headers=mira)
    assert _numbers(client, lead) == (1, 1, 0)
    _accept(client, avery)
    assert _numbers(client, lead) == (1, 0, None)

    clock.advance(seconds=1)
    client.post("/chat/live", headers=jon)
    clock.advance(seconds=50)
    assert _numbers(client, lead) == (1, 1, 50)
    clock.advance(seconds=9)
    client.get("/chat", headers=jon)
    [third] = _customers(1)
    client.post("/chat/live", headers=_chat(client, third))
    assert _numbers(client, lead) == (1, 2, 59)

    # Avery's desk has not checked in for 60 seconds: nobody is available, and the line stays.
    clock.advance(seconds=1)
    assert _numbers(client, lead) == (0, 2, 60)
    client.get("/live", headers=avery)
    assert _numbers(client, lead) == (1, 2, 60)


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_the_average_chat_length_is_the_median_the_wait_estimate_uses(client, clock):
    lead = _lead(client)
    # Too few live chats in the last 7 days: no number, as the customer's estimate says "a few minutes".
    _history(clock, 4, 6, 8, 30)
    _history(clock, 60, 60, 60, days_ago=8)
    assert _line(client, lead)["average_chat_minutes"] is None

    _history(clock, 5)
    assert _line(client, lead)["average_chat_minutes"] == 6

    # The customer's estimate uses the same number: one slot, one customer ahead, about 2 x 6 minutes.
    customers = _customers(3)
    avery = _avery(client)
    client.post("/presence", headers=avery, json={"state": "available"})
    with _db() as conn:
        conn.execute("UPDATE specialist_availability SET capacity = 1")
    for body in customers:
        clock.advance(seconds=1)
        client.post("/chat/live", headers=_chat(client, body))
    _accept(client, avery)
    assert client.get("/chat", headers=_chat(client, customers[2])).json()["status"] == (
        "You are number 2 in line. The wait is about 8 to 18 minutes."
    )


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_an_alert_appears_for_a_request_offered_3_times_until_the_customer_leaves_a_message(client):
    _add_sam()
    _add_lee()
    chat, lead = _chat(client), _lead(client)
    specialists = [_avery(client), _sam(client), _staff(client, LEE, "northstar-third")]
    for staff in specialists:
        client.post("/presence", headers=staff, json={"state": "available"})
    client.post("/chat/live", headers=chat)
    case_id = _case()

    for _ in range(2):
        holder = _holder(client, specialists)
        client.post(f"/live/{_offer(client, holder)}/decline", headers=holder)
        assert _line(client, lead)["alerts"] == []
    holder = _holder(client, specialists)
    client.post(f"/live/{_offer(client, holder)}/decline", headers=holder)

    view = _line(client, lead)
    assert view["alerts"] == [{"kind": "unanswered", "case_id": case_id, "customer": "Mira Shah", "offers": 3}]
    # The request left the line.
    assert view["line_length"] == 0

    # Once the customer leaves a message, the escalations inbox holds it, and the alert is gone.
    assert client.post("/chat/leave-message", headers=chat, json={"text": "Please call me."}).status_code == 200
    assert _line(client, lead)["alerts"] == []


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_a_customer_waiting_more_than_2_minutes_for_a_reply_is_flagged_and_the_chat_is_not_reassigned(client, clock):
    _add_sam()
    chat, avery, sam, lead = _chat(client), _avery(client), _sam(client), _lead(client)
    client.post("/presence", headers=avery, json={"state": "available"})
    client.post("/chat/live", headers=chat)
    case_id = _case()
    offer = _accept(client, avery)
    client.post(f"/live/{offer}/messages", headers=avery, json={"text": "Hi Mira, this is Avery."})
    clock.advance(seconds=30)
    _say(client, chat, "The seam on my coat is torn.")
    client.post("/presence", headers=sam, json={"state": "available"})

    clock.advance(seconds=120)
    assert _line(client, lead)["alerts"] == []
    clock.advance(seconds=1)
    for staff in (avery, sam):
        client.get("/live", headers=staff)
    assert _line(client, lead)["alerts"] == [
        {"kind": "no_reply", "case_id": case_id, "customer": "Mira Shah", "specialist": "Avery", "waiting_seconds": 121}
    ]

    # Read-only: the live chat stays with Avery, and nobody else is offered it.
    clock.advance(minutes=5)
    for staff in (avery, sam):
        client.get("/live", headers=staff)
    assert _line(client, lead)["alerts"][0]["waiting_seconds"] == 421
    assert [held["customer"] for held in client.get("/live", headers=avery).json()["chats"]] == ["Mira Shah"]
    sams = client.get("/live", headers=sam).json()
    assert sams["state"] == "available" and sams["offers"] == [] and sams["chats"] == []
    assert client.get("/chat/state", headers=chat).json()["live"] == {"status": "active", "specialist": "Avery"}
    with _db() as conn:
        assert conn.execute("SELECT status, staff_id FROM live_chat_requests").fetchone() == {
            "status": "active",
            "staff_id": staff_id_for("specialist@northstar.example"),
        }

    # Avery replies, and the alert is gone.
    client.post(f"/live/{offer}/messages", headers=avery, json={"text": "Sorry for the wait. Let me look."})
    assert _line(client, lead)["alerts"] == []


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_the_wait_for_a_reply_starts_when_the_specialist_accepts(client, clock):
    mira, jon, avery, lead = _chat(client, MIRA), _chat(client, JON), _avery(client), _lead(client)
    # Mira wrote to the agent long before she asked for a person. Jon asks without writing at all.
    _say(client, mira, "How long may apparel and footwear be returned?")
    clock.advance(minutes=10)
    client.post("/presence", headers=avery, json={"state": "available"})
    client.post("/chat/live", headers=mira)
    clock.advance(seconds=1)
    client.post("/chat/live", headers=jon)
    _accept(client, avery)
    _accept(client, avery)
    assert _line(client, lead)["alerts"] == []

    clock.advance(seconds=121)
    assert [(alert["customer"], alert["waiting_seconds"]) for alert in _line(client, lead)["alerts"]] == [
        ("Mira Shah", 121),
        ("Jon Hale", 121),
    ]


@pytest.mark.parametrize("client", [{"live_agents_enabled": True, "quiet_specialist_minutes": 5}], indirect=True)
def test_the_wait_before_a_quiet_specialist_is_flagged_is_a_setting(client, clock):
    chat, avery, lead = _chat(client), _avery(client), _lead(client)
    client.post("/presence", headers=avery, json={"state": "available"})
    client.post("/chat/live", headers=chat)
    _accept(client, avery)
    clock.advance(minutes=5)
    assert _line(client, lead)["alerts"] == []
    clock.advance(seconds=1)
    assert [alert["kind"] for alert in _line(client, lead)["alerts"]] == ["no_reply"]
