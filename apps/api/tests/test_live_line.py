"""The line and the wait estimate (issue #140, R40, R41).

A waiting customer sees their place and a wait range. Nobody available or a wait over the cap offers
to leave a message instead. A chat that stops refreshing leaves the line, and the customer can leave it.
"""

import uuid
from datetime import timedelta

import pytest
from conftest import TEST_URL
from northstar.cases import LINE_REFUSED_TEXT, OFFERED_TEXT, CaseStore, wait_minutes, wait_range
from northstar.identity.service import staff_id_for
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from test_live_chat import JON, LIVE, MIRA, _add_sam, _avery, _chat, _customers, _db, _lead, _sam, _say

FEW = "The wait is a few minutes."


def _join(client, clock, body) -> dict:
    """A customer starts a chat a second later than the last one and asks for a person."""
    clock.advance(seconds=1)
    chat = _chat(client, body)
    assert client.post("/chat/live", headers=chat).status_code == 200
    return chat


def _busy(client, clock, specialist, customers) -> list[dict]:
    """The specialist sets Available, and these customers take their slots as offers."""
    client.post("/presence", headers=specialist, json={"state": "available"})
    return [_join(client, clock, body) for body in customers]


def _held(client, specialist) -> None:
    """The specialist accepts every offer. Live chats hold the slots for minutes; offers expire (issue #139)."""
    for offer in client.get("/live", headers=specialist).json()["offers"]:
        assert client.post(f"/live/{offer['id']}/accept", headers=specialist).status_code == 200


def _status(client, chat) -> str:
    return client.get("/chat", headers=chat).json()["status"]


def _history(clock, *minutes: float, days_ago: float = 0) -> None:
    """Live chats of these lengths, ended this many days ago, on a resolved case of Mira's."""
    ended = clock.now() - timedelta(days=days_ago)
    with _db() as conn:
        case_id = uuid.uuid4()
        conn.execute(
            """
            INSERT INTO cases (id, staff_id, customer_id, status, created_at)
            SELECT %s, %s, id, 'Resolved', %s FROM customers WHERE email = %s
            """,
            (case_id, staff_id_for("specialist@northstar.example"), ended, MIRA["email"]),
        )
        for length in minutes:
            conn.execute(
                """
                INSERT INTO live_chat_requests (id, case_id, customer_id, reason, status, staff_id, queued_at, accepted_at, ended_at)
                SELECT %s, %s, customer_id, 'requested', 'ended', %s, %s, %s, %s FROM cases WHERE id = %s
                """,
                (
                    uuid.uuid4(),
                    case_id,
                    staff_id_for("specialist@northstar.example"),
                    ended - timedelta(minutes=length + 1),
                    ended - timedelta(minutes=length),
                    ended,
                    case_id,
                ),
            )


def _line() -> list[str]:
    with _db() as conn:
        return [row["status"] for row in conn.execute("SELECT status FROM live_chat_requests ORDER BY queued_at, id")]


def test_the_estimate_for_the_worked_example():
    # Two specialists with two slots each, and a 6-minute average: four chats end about every 6 minutes.
    assert wait_minutes(1, 6, 4) == 1.5
    assert wait_minutes(4, 6, 4) == 6
    assert wait_range(1.5) == (1, 2)
    assert wait_range(6) == (4, 9)
    assert wait_range(0.4) == (1, 1)


def test_with_the_setting_off_there_is_no_line_to_leave(client):
    chat = _chat(client)
    assert client.delete("/chat/live", headers=chat).status_code == 404
    assert _status(client, chat) == ""


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_waiting_customers_see_their_place_and_the_wait_as_a_range(client, clock):
    _add_sam()
    _history(clock, 5, 6, 6, 7, 30)
    # Older than 7 days, so not counted: it would raise the median.
    _history(clock, 60, 60, 60, days_ago=8)
    customers = _customers(8)
    _busy(client, clock, _avery(client), customers[:2])
    _busy(client, clock, _sam(client), customers[2:4])
    waiting = [_join(client, clock, body) for body in customers[4:]]

    assert [_status(client, chat) for chat in waiting] == [
        "You are number 1 in line. The wait is about 1 to 2 minutes.",
        "You are number 2 in line. The wait is about 2 to 4 minutes.",
        "You are number 3 in line. The wait is about 3 to 7 minutes.",
        "You are number 4 in line. The wait is about 4 to 9 minutes.",
    ]
    assert _status(client, _chat(client, customers[0])) == OFFERED_TEXT
    # GET /chat keeps its shape, and /chat/state keeps its keys.
    assert set(client.get("/chat", headers=waiting[0]).json()) == {"status", "messages"}
    assert client.get("/chat/state", headers=waiting[0]).json() == {
        "follow_up": None,
        "live_enabled": True,
        "live": {"status": "waiting", "specialist": None},
    }


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_with_fewer_than_five_live_chats_in_seven_days_the_wait_is_a_few_minutes(client, clock):
    _history(clock, 6, 6, 6, 6)
    _history(clock, 6, days_ago=8)
    customers = _customers(3)
    _busy(client, clock, _avery(client), customers[:2])
    assert _status(client, _join(client, clock, customers[2])) == f"You are number 1 in line. {FEW}"


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_the_line_is_escalated_first_then_oldest(client, clock):
    customers = _customers(5)
    avery = _avery(client)
    _busy(client, clock, avery, customers[:2])
    first, second = _join(client, clock, customers[2]), _join(client, clock, customers[3])
    # The agent's escalation joins the line through the same call (issue #141 wires it).
    clock.advance(seconds=1)
    escalated = customers[4]
    with ConnectionPool(TEST_URL, min_size=1, max_size=1, kwargs={"row_factory": dict_row}) as pool:
        customer_id = CaseStore(pool, clock).chat_customer(escalated["order_id"], escalated["email"])
        assert CaseStore(pool, clock, live_chat=True).request_live(customer_id, reason="escalated") is True
    escalated_chat = _chat(client, escalated)
    for place, chat in enumerate((escalated_chat, first, second), start=1):
        assert _status(client, chat) == f"You are number {place} in line. {FEW}"

    # Each freed slot goes to the front of the line.
    for after in (escalated_chat, first):
        offer = client.get("/live", headers=avery).json()["offers"][0]["id"]
        assert client.post(f"/live/{offer}/accept", headers=avery).status_code == 200
        assert client.post(f"/live/{offer}/resolve", headers=avery).status_code == 200
        assert _status(client, after) == OFFERED_TEXT
    assert _status(client, second).startswith("You are number 1 in line.")


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_with_no_specialist_available_the_customer_may_leave_a_message(client):
    chat = _chat(client)
    assert client.post("/chat/live", headers=chat).json() == {"live": None}
    assert client.get("/chat/state", headers=chat).json() == {"follow_up": "leave_message", "live_enabled": True, "live": None}
    assert _status(client, chat) == LINE_REFUSED_TEXT
    # The agent still answers, and the offer stands.
    assert _say(client, chat, "How long is the return window?")["messages"][-1]["role"] == "assistant"
    assert client.get("/chat/state", headers=chat).json()["follow_up"] == "leave_message"

    left = client.post("/chat/leave-message", headers=chat, json={"text": "Please call me about my coat."})
    assert left.status_code == 200
    assert left.json()["status"].startswith("A specialist will follow up with you.")
    [item] = client.get("/inbox", headers=_lead(client)).json()
    assert "Please call me about my coat." in item["handoff"]
    assert _line() == ["refused"]


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_over_the_longest_wait_the_customer_may_leave_a_message(client, clock):
    # One specialist with two slots and 30-minute chats: place 1 waits about 15 minutes, place 2 about 30.
    _history(clock, 30, 30, 30, 30, 30)
    customers = _customers(4)
    avery = _avery(client)
    _busy(client, clock, avery, customers[:2])
    first = _join(client, clock, customers[2])
    assert _status(client, first) == "You are number 1 in line. The wait is about 10 to 22 minutes."

    second = _join(client, clock, customers[3])
    assert client.get("/chat/state", headers=second).json() == {"follow_up": "leave_message", "live_enabled": True, "live": None}
    assert _status(client, second) == LINE_REFUSED_TEXT
    assert _line()[-1] == "refused"

    # Asking again once a slot frees joins the line, and the offer is gone.
    offer = client.get("/live", headers=avery).json()["offers"][0]["id"]
    client.post(f"/live/{offer}/accept", headers=avery)
    client.post(f"/live/{offer}/resolve", headers=avery)
    clock.advance(seconds=1)
    assert client.post("/chat/live", headers=second).json() == {"live": {"status": "waiting", "specialist": None}}
    assert client.get("/chat/state", headers=second).json()["follow_up"] is None


@pytest.mark.parametrize("client", [{"live_chat_enabled": True, "longest_wait_minutes": 30}], indirect=True)
def test_the_longest_wait_is_a_setting(client, clock):
    _history(clock, 30, 30, 30, 30, 30)
    customers = _customers(4)
    _busy(client, clock, _avery(client), customers[:2])
    _join(client, clock, customers[2])
    second = _join(client, clock, customers[3])
    assert _status(client, second) == "You are number 2 in line. The wait is about 21 to 45 minutes."


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_a_chat_that_stops_refreshing_leaves_the_line_and_rejoins_at_the_back(client, clock):
    customers = _customers(2)
    avery = _avery(client)
    _busy(client, clock, avery, customers)
    _held(client, avery)
    mira, jon = _join(client, clock, MIRA), _join(client, clock, JON)

    # Jon's chat refreshes, and so does Avery's desk. Mira's does not, and at 2 minutes she is out of the line.
    clock.advance(minutes=1)
    client.get("/live", headers=avery)
    assert _status(client, jon) == f"You are number 2 in line. {FEW}"
    clock.advance(seconds=58)
    client.get("/live", headers=avery)
    assert _status(client, jon) == f"You are number 2 in line. {FEW}"
    clock.advance(seconds=1)
    assert _status(client, jon) == f"You are number 1 in line. {FEW}"
    assert _line()[2:] == ["abandoned", "waiting"]

    # A freed slot skips her. Back, she joins at the back.
    assert _status(client, mira) == f"You are number 2 in line. {FEW}"
    assert _line()[2:] == ["abandoned", "waiting", "waiting"]
    held = client.get("/live", headers=avery).json()["chats"][0]["id"]
    client.post(f"/live/{held}/resolve", headers=avery)
    assert _status(client, jon) == OFFERED_TEXT
    assert _status(client, mira) == f"You are number 1 in line. {FEW}"


@pytest.mark.parametrize("client", [{"live_chat_enabled": True, "line_gone_minutes": 5}], indirect=True)
def test_the_time_before_a_quiet_chat_leaves_the_line_is_a_setting(client, clock):
    avery = _avery(client)
    _busy(client, clock, avery, _customers(2))
    _held(client, avery)
    _join(client, clock, MIRA)
    jon = _join(client, clock, JON)
    clock.advance(minutes=4)
    client.get("/live", headers=avery)
    assert _status(client, jon) == f"You are number 2 in line. {FEW}"
    clock.advance(minutes=1)
    client.get("/live", headers=avery)
    assert _status(client, jon) == f"You are number 1 in line. {FEW}"


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_the_customer_can_leave_the_line_and_go_back_to_the_agent(client, clock):
    customers = _customers(2)
    avery = _avery(client)
    fillers = _busy(client, clock, avery, customers)
    mira, jon = _join(client, clock, MIRA), _join(client, clock, JON)

    assert client.delete("/chat/live", headers=mira).json() == {"live": None}
    assert client.get("/chat/state", headers=mira).json() == {"follow_up": None, "live_enabled": True, "live": None}
    assert client.delete("/chat/live", headers=mira).status_code == 409
    assert _status(client, jon) == f"You are number 1 in line. {FEW}"
    view = _say(client, mira, "How long is the return window?")
    assert view["status"] == "" and view["messages"][-1]["role"] == "assistant"

    # Leaving while offered withdraws the offer, and the slot goes to the next in line.
    assert client.delete("/chat/live", headers=fillers[0]).status_code == 200
    assert [offer["customer"] for offer in client.get("/live", headers=avery).json()["offers"]] == ["Live Customer1", "Jon Hale"]
    assert _status(client, jon) == OFFERED_TEXT


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_the_agent_answers_while_the_customer_waits_and_stops_once_a_specialist_accepts(client, clock, monkeypatch):
    customers = _customers(2)
    avery = _avery(client)
    _busy(client, clock, avery, customers)
    mira = _join(client, clock, MIRA)

    view = _say(client, mira, "How long may apparel and footwear be returned?")
    assert view["messages"][-1]["role"] == "assistant"
    assert view["status"] == f"You are number 1 in line. {FEW}"
    # A gated action raised while waiting still goes to a lead.
    view = _say(client, mira, "Please refund order NS-1001.")
    assert "Nothing is approved yet" in view["status"]
    assert [item["order_id"] for item in client.get("/approvals", headers=_lead(client)).json()] == ["NS-1001"]

    # A slot frees, Avery accepts Mira, and the agent goes quiet.
    offer = client.get("/live", headers=avery).json()["offers"][0]["id"]
    client.post(f"/live/{offer}/accept", headers=avery)
    client.post(f"/live/{offer}/resolve", headers=avery)
    [offer] = [o["id"] for o in client.get("/live", headers=avery).json()["offers"] if o["customer"] == "Mira Shah"]
    assert client.post(f"/live/{offer}/accept", headers=avery).status_code == 200
    assert client.get("/chat/state", headers=mira).json()["live"] == {"status": "active", "specialist": "Avery"}
    monkeypatch.setattr(CaseStore, "ask", lambda *args, **kwargs: pytest.fail("the agent took a turn"))
    assert _say(client, mira, "Thanks for taking this.")["messages"][-1] == {"role": "user", "text": "Thanks for taking this."}
