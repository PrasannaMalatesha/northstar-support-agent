"""Live chat (issue #138): a customer asks for a person, and an available specialist takes the chat.

The line is rows in Postgres, and one assignment function makes the offers (ADR 0001).
"""

import threading
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest
from conftest import SECRET, TEST_URL
from fastapi.testclient import TestClient
from northstar.cases import CaseStore
from northstar.identity.postgres import PostgresIdentityStore
from northstar.identity.service import hash_password, staff_id_for
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from northstar_api.main import create_app
from northstar_api.settings import Settings

LIVE = [{"live_agents_enabled": True}]
MIRA = {"order_id": "NS-1001", "email": "mira.shah@northstar.example"}
JON = {"order_id": "NS-1002", "email": "jon.hale@northstar.example"}
SAM = "sam.ortiz@northstar.example"


def _staff(client, email, password) -> dict:
    token = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _avery(client) -> dict:
    return _staff(client, "specialist@northstar.example", "northstar-specialist")


def _sam(client) -> dict:
    return _staff(client, SAM, "northstar-second")


def _lead(client) -> dict:
    return _staff(client, "lead@northstar.example", "northstar-lead")


def _chat(client, body=MIRA) -> dict:
    started = client.post("/chat/start", json=body)
    assert started.status_code == 200, started.text
    return {"Authorization": f"Bearer {started.json()['chat_token']}"}


def _say(client, chat, question: str) -> dict:
    sent = client.post("/chat/messages", headers=chat, json={"question": question})
    assert sent.status_code == 200, sent.text
    return sent.json()


def _db():
    return psycopg.connect(TEST_URL, row_factory=dict_row)


def _add_sam() -> None:
    with ConnectionPool(TEST_URL, min_size=1, max_size=1, kwargs={"row_factory": dict_row}) as pool:
        PostgresIdentityStore(pool).upsert_staff(staff_id_for(SAM), SAM, "Sam Ortiz", hash_password("northstar-second"), "specialist")


def _customers(count: int) -> list[dict]:
    """Extra customers with one order each, so each can open their own chat."""
    with _db() as conn:
        for n in range(count):
            email = f"live.customer{n}@example.test"
            conn.execute(
                "INSERT INTO customers (id, name, email, phone) VALUES (%s, %s, %s, %s) ON CONFLICT (email) DO NOTHING",
                (uuid.uuid5(uuid.NAMESPACE_URL, email), f"Live Customer{n}", email, f"55501{n:05d}"),
            )
            conn.execute(
                """
                INSERT INTO orders (id, customer_id, status, purchased_on, lines, refunds)
                VALUES (%s, %s, 'delivered', '2026-09-20', 'Canvas tote', 'none') ON CONFLICT (id) DO NOTHING
                """,
                (f"NS-L{n:03d}", uuid.uuid5(uuid.NAMESPACE_URL, email)),
            )
    return [{"order_id": f"NS-L{n:03d}", "email": f"live.customer{n}@example.test"} for n in range(count)]


def _live_events() -> list[str]:
    with _db() as conn:
        return [row["event"] for row in conn.execute("SELECT event FROM audit_log WHERE event LIKE 'live_chat_%' ORDER BY id")]


def _requests() -> list[dict]:
    with _db() as conn:
        return conn.execute("SELECT status, staff_id, customer_id FROM live_chat_requests").fetchall()


def _accepted(client, chat, specialist) -> str:
    """The customer asks for a person, and the specialist sets Available and accepts the offer."""
    assert client.post("/chat/live", headers=chat).status_code == 200
    client.post("/presence", headers=specialist, json={"state": "available"})
    offer = client.get("/live", headers=specialist).json()["offers"][0]["id"]
    assert client.post(f"/live/{offer}/accept", headers=specialist).status_code == 200
    return offer


def test_with_the_setting_off_no_live_chat_route_works(client):
    chat, avery = _chat(client), _avery(client)
    assert client.get("/chat/state", headers=chat).json() == {"offer": None, "live_enabled": False, "live": None}
    assert client.post("/chat/live", headers=chat).status_code == 404
    assert client.post("/chat/renew", headers=chat).status_code == 404
    assert client.post("/presence", headers=avery, json={"state": "available"}).status_code == 404
    assert client.get("/live", headers=avery).status_code == 404
    for action in ("accept", "messages", "resolve", "escalate"):
        assert client.post(f"/live/{uuid.uuid4()}/{action}", headers=avery, json={}).status_code == 404


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_a_customer_talks_to_a_specialist_who_resolves_the_case(client, monkeypatch):
    chat, avery = _chat(client), _avery(client)
    _say(client, chat, "How long may apparel and footwear be returned?")
    assert client.get("/chat/state", headers=chat).json() == {"offer": None, "live_enabled": True, "live": None}

    # Nobody is available yet: the request waits, and the agent still answers.
    assert client.post("/chat/live", headers=chat).json() == {"live": {"status": "waiting", "specialist": None}}
    assert client.post("/chat/live", headers=chat).status_code == 200
    assert len(_requests()) == 1
    assert _say(client, chat, "How long is the return window?")["messages"][-1]["role"] == "assistant"
    assert client.get("/live", headers=avery).json() == {"state": "away", "offers": [], "chats": []}

    client.post("/presence", headers=avery, json={"state": "available"})
    live = client.get("/live", headers=avery).json()
    assert live["state"] == "available" and live["chats"] == []
    assert [offer["customer"] for offer in live["offers"]] == ["Mira Shah"]
    assert client.get("/chat/state", headers=chat).json()["live"] == {"status": "offered", "specialist": None}

    offer = live["offers"][0]["id"]
    assert client.post(f"/live/{offer}/accept", headers=avery).status_code == 200
    assert client.get("/chat/state", headers=chat).json()["live"] == {"status": "active", "specialist": "Avery"}
    [held] = client.get("/live", headers=avery).json()["chats"]
    assert held["id"] == offer and held["customer"] == "Mira Shah"
    assert [m["role"] for m in held["messages"]] == ["user", "assistant", "user", "assistant"]

    text = "Hi Mira, I am Avery. Call me back on 512-555-0199 if we get cut off."
    assert client.post(f"/live/{offer}/messages", headers=avery, json={"text": text}).status_code == 200
    view = client.get("/chat", headers=chat).json()
    assert set(view) == {"status", "messages"}
    assert view["messages"][-1] == {
        "role": "specialist",
        "name": "Avery",
        "text": "Hi Mira, I am Avery. Call me back on [phone] if we get cut off.",
    }

    # The agent is quiet while a specialist holds the chat: no turn, so no model call and no limit charged.
    monkeypatch.setattr(CaseStore, "ask", lambda *args, **kwargs: pytest.fail("the agent took a turn"))
    with _db() as conn:
        counted = conn.execute("SELECT sum(requests) AS n FROM daily_limits").fetchone()["n"]
    view = _say(client, chat, "Thanks Avery. My email is mira.shah@northstar.example.")
    assert view["messages"][-1] == {"role": "user", "text": "Thanks Avery. My email is [email]."}
    with _db() as conn:
        assert conn.execute("SELECT sum(requests) AS n FROM daily_limits").fetchone()["n"] == counted
    assert client.get("/live", headers=avery).json()["chats"][0]["messages"][-1]["text"] == "Thanks Avery. My email is [email]."
    monkeypatch.undo()

    assert client.post(f"/live/{offer}/resolve", headers=avery).status_code == 200
    assert client.get(f"/cases/{held['case_id']}", headers=_lead(client)).json()["status"] == "Resolved"
    assert client.get("/live", headers=avery).json()["chats"] == []
    assert client.get("/chat/state", headers=chat).json()["live"] is None
    view = client.get("/chat", headers=chat).json()
    assert view["status"] == "This chat is closed. Write again to start a new one."
    assert view["messages"][-1]["text"] == "Thanks Avery. My email is [email]."
    assert _live_events() == [
        "live_chat_requested",
        "live_chat_offered",
        "live_chat_accepted",
        "live_chat_message",
        "live_chat_ended",
    ]

    # Writing again starts a new case, and the agent answers it.
    after = _say(client, chat, "How long is the return window?")
    assert after["status"] == "" and after["messages"][-1]["role"] == "assistant"


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_an_escalated_live_chat_lands_in_the_escalations_inbox_with_a_handoff(client):
    chat, avery = _chat(client), _avery(client)
    _say(client, chat, "Where is order NS-1009?")
    offer = _accepted(client, chat, avery)
    note = "The carrier needs a trace. Payments should call the customer."
    assert client.post(f"/live/{offer}/escalate", headers=avery, json={"note": "  "}).status_code == 422
    assert client.post(f"/live/{offer}/escalate", headers=avery, json={"note": note}).status_code == 200

    [item] = client.get("/inbox", headers=_lead(client)).json()
    assert item["source"] == "chat" and item["customer"] == "Mira Shah" and item["assigned_to"] is None
    assert f"Specialist note: {note}" in item["handoff"] and "NS-1009" in item["handoff"]
    assert client.get("/chat", headers=chat).json()["status"].startswith("A specialist will follow up with you.")
    assert client.get("/chat/state", headers=chat).json()["live"] is None
    assert _live_events()[-1] == "live_chat_ended"


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_a_specialist_posts_only_into_their_own_live_chat_and_leads_take_none(client):
    _add_sam()
    chat, avery, sam, lead = _chat(client), _avery(client), _sam(client), _lead(client)
    assert client.post("/chat/live", headers=chat).status_code == 200
    client.post("/presence", headers=avery, json={"state": "available"})
    offer = client.get("/live", headers=avery).json()["offers"][0]["id"]
    reply = {"text": "Hello from the team."}

    # Offered is not joined: nobody posts yet, and only Avery can accept.
    assert client.post(f"/live/{offer}/messages", headers=avery, json=reply).status_code == 403
    assert client.post(f"/live/{offer}/accept", headers=sam).status_code == 403
    assert client.post(f"/live/{offer}/accept", headers=avery).status_code == 200
    assert client.post(f"/live/{offer}/accept", headers=avery).status_code == 403

    for action, body in (("messages", reply), ("resolve", None), ("escalate", {"note": "Taking over."})):
        assert client.post(f"/live/{offer}/{action}", headers=sam, json=body).status_code == 403
        assert client.post(f"/live/{offer}/{action}", headers=lead, json=body).status_code == 403
    assert client.post(f"/live/{offer}/messages", headers=avery, json={"text": "   "}).status_code == 422
    assert client.post(f"/live/{uuid.uuid4()}/messages", headers=avery, json=reply).status_code == 403
    assert client.post("/live/not-an-id/messages", headers=avery, json=reply).status_code == 422
    assert client.post("/presence", headers=lead, json={"state": "available"}).status_code == 403
    assert client.get("/live", headers=lead).status_code == 403
    assert client.get("/live", headers=chat).status_code == 401
    assert client.post("/chat/live", headers=avery).status_code == 401
    assert [m["role"] for m in client.get("/chat", headers=chat).json()["messages"]] == []
    assert "live_chat_message" not in _live_events()


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_the_most_spare_capacity_gets_the_offer_and_an_ended_chat_frees_a_slot(client, clock):
    _add_sam()
    extra = _customers(2)
    mira, jon, third, fourth = _chat(client, MIRA), _chat(client, JON), _chat(client, extra[0]), _chat(client, extra[1])
    avery, sam = _avery(client), _sam(client)
    first = _accepted(client, mira, avery)

    # Sam has two free slots and Avery one, so Sam gets the next request.
    client.post("/presence", headers=sam, json={"state": "available"})
    clock.advance(minutes=1)
    client.post("/chat/live", headers=jon)
    assert [offer["customer"] for offer in client.get("/live", headers=sam).json()["offers"]] == ["Jon Hale"]

    # Avery goes away: Sam takes the next request too, and the one after waits for a free slot.
    client.post("/presence", headers=avery, json={"state": "away"})
    clock.advance(minutes=1)
    client.post("/chat/live", headers=third)
    clock.advance(minutes=1)
    client.post("/chat/live", headers=fourth)
    assert [offer["customer"] for offer in client.get("/live", headers=sam).json()["offers"]] == ["Jon Hale", "Live Customer0"]
    assert client.get("/chat/state", headers=fourth).json()["live"]["status"] == "waiting"

    # Avery is still in the first chat while away. Ending it and coming back frees a slot for the waiting customer.
    client.post(f"/live/{first}/resolve", headers=avery)
    assert client.get("/chat/state", headers=fourth).json()["live"]["status"] == "waiting"
    client.post("/presence", headers=avery, json={"state": "available"})
    assert [offer["customer"] for offer in client.get("/live", headers=avery).json()["offers"]] == ["Live Customer1"]


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_the_offer_to_leave_a_message_is_hidden_while_a_person_is_on_the_way(client):
    chat = _chat(client)
    for question in ("What is your favorite color?", "Tell me a joke.", "Who won the game last night?"):
        _say(client, chat, question)
    assert client.get("/chat/state", headers=chat).json()["offer"] == "leave_message"
    client.post("/chat/live", headers=chat)
    assert client.get("/chat/state", headers=chat).json() == {
        "offer": None,
        "live_enabled": True,
        "live": {"status": "waiting", "specialist": None},
    }
    assert client.post("/chat/leave-message", headers=chat, json={"text": "Please call me."}).status_code == 409


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_the_chat_token_is_renewed_while_a_request_is_open(client, clock):
    chat = _chat(client)
    assert client.post("/chat/renew", headers=chat).status_code == 409
    client.post("/chat/live", headers=chat)
    clock.advance(minutes=25)
    renewed = client.post("/chat/renew", headers=chat)
    assert renewed.status_code == 200
    clock.advance(minutes=10)
    assert client.get("/chat", headers=chat).status_code == 401
    fresh = {"Authorization": f"Bearer {renewed.json()['chat_token']}"}
    assert client.get("/chat/state", headers=fresh).json()["live"] == {"status": "waiting", "specialist": None}


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_ten_customers_and_two_specialists_with_two_slots_each_give_exactly_four_offers(client, clock):
    _add_sam()
    customers = _customers(10)
    settings = Settings(database_url=TEST_URL, token_secret=SECRET, live_agents_enabled=True)
    # Its own pool: twelve requests at once, each holding a connection while it waits for row locks.
    with ConnectionPool(TEST_URL, min_size=1, max_size=14, kwargs={"row_factory": dict_row}) as pool:
        with TestClient(create_app(settings=settings, clock=clock, pool=pool)) as api:
            chats = [_chat(api, body) for body in customers]
            specialists = [_avery(api), _sam(api)]
            start = threading.Barrier(len(chats) + len(specialists))

            def at_once(call):
                start.wait()
                return call()

            calls = [lambda chat=chat: api.post("/chat/live", headers=chat) for chat in chats] + [
                lambda staff=staff: api.post("/presence", headers=staff, json={"state": "available"})
                for staff in specialists
            ]
            with ThreadPoolExecutor(max_workers=len(calls)) as workers:
                assert all(response.status_code == 200 for response in workers.map(at_once, calls))

            offered = [row for row in _requests() if row["status"] == "offered"]
            assert len(offered) == 4 and len({row["customer_id"] for row in offered}) == 4
            assert Counter(row["staff_id"] for row in offered) == {staff_id_for("specialist@northstar.example"): 2, staff_id_for(SAM): 2}
            assert Counter(row["status"] for row in _requests()) == {"offered": 4, "waiting": 6}
            assert _live_events().count("live_chat_offered") == 4

            # More slots, then the assignment run from many threads at once: each slot is filled once.
            with _db() as conn:
                conn.execute("UPDATE specialist_availability SET capacity = 3")
            store = CaseStore(pool, clock, live_chats=True)
            start = threading.Barrier(8)
            with ThreadPoolExecutor(max_workers=8) as workers:
                list(workers.map(lambda _: at_once(store._assign), range(8)))
            offered = [row for row in _requests() if row["status"] == "offered"]
            assert len(offered) == 6 and len({row["customer_id"] for row in offered}) == 6
            assert set(Counter(row["staff_id"] for row in offered).values()) == {3}
            assert _live_events().count("live_chat_offered") == 6
