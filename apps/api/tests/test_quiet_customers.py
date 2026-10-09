"""Quiet customers free the specialist (issue #142, R44).

The clock runs from the specialist's last message, and only while the customer has not answered it.
Timers apply when a chat, a live view, or the line is read, so each step advances the test clock and reads.
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest
from conftest import TEST_URL
from northstar.cases import CaseStore
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from northstar_api.settings import Settings

LIVE = [{"live_agents_enabled": True}]
MIRA = {"order_id": "NS-1001", "email": "mira.shah@northstar.example"}
JON = {"order_id": "NS-1002", "email": "jon.hale@northstar.example"}
ANSWER = "Your refund is on its way. Is there anything else?"
CLOSED = "This chat is closed. Write again to start a new one."


def _staff(client, email, password) -> dict:
    token = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _avery(client) -> dict:
    return _staff(client, "specialist@northstar.example", "northstar-specialist")


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


def _events() -> list[str]:
    with _db() as conn:
        return [row["event"] for row in conn.execute("SELECT event FROM audit_log WHERE event LIKE 'live_chat_%' ORDER BY id")]


def _one_slot() -> None:
    with _db() as conn:
        conn.execute("UPDATE specialist_availability SET capacity = 1")


def _third_customer() -> dict:
    email = "quiet.customer@example.test"
    customer_id = uuid.uuid5(uuid.NAMESPACE_URL, email)
    with _db() as conn:
        conn.execute(
            "INSERT INTO customers (id, name, email, phone) VALUES (%s, 'Quiet Customer', %s, '5550142999') ON CONFLICT (email) DO NOTHING",
            (customer_id, email),
        )
        conn.execute(
            """
            INSERT INTO orders (id, customer_id, status, purchased_on, lines, refunds)
            VALUES ('NS-Q001', %s, 'delivered', '2026-09-20', 'Canvas tote', 'none') ON CONFLICT (id) DO NOTHING
            """,
            (customer_id,),
        )
    return {"order_id": "NS-Q001", "email": email}


def _state(client, chat) -> dict | None:
    return client.get("/chat/state", headers=chat).json()["live"]


def _chats(client, specialist) -> list[tuple[str, bool]]:
    return [(chat["customer"], chat["idle"]) for chat in client.get("/live", headers=specialist).json()["chats"]]


def _answered(client, chat, specialist) -> dict:
    """The specialist is available, the customer asks for a person, and the specialist accepts and answers.

    The quiet clock starts. The line turns a customer away when nobody is available, so Available comes first.
    """
    client.post("/presence", headers=specialist, json={"state": "available"})
    assert client.post("/chat/live", headers=chat).status_code == 200
    offer = client.get("/live", headers=specialist).json()["offers"][0]["id"]
    assert client.post(f"/live/{offer}/accept", headers=specialist).status_code == 200
    assert client.post(f"/live/{offer}/messages", headers=specialist, json={"text": ANSWER}).status_code == 200
    [held] = client.get("/live", headers=specialist).json()["chats"]
    return held


def test_the_times_default_to_2_3_and_15_minutes():
    settings = Settings(database_url=TEST_URL)
    assert (settings.quiet_nudge_minutes, settings.quiet_idle_minutes, settings.quiet_close_minutes) == (2, 3, 15)


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_the_nudge_comes_at_2_minutes_the_slot_frees_at_3_and_the_chat_closes_at_15(client, clock):
    chat, jon, avery = _chat(client, MIRA), _chat(client, JON), _avery(client)
    held = _answered(client, chat, avery)
    _one_slot()
    clock.advance(minutes=1)
    client.post("/chat/live", headers=jon)
    assert _state(client, jon)["status"] == "waiting"

    clock.advance(seconds=59)
    assert client.get("/chat", headers=chat).json()["status"] == ""
    clock.advance(seconds=1)
    assert client.get("/chat", headers=chat).json()["status"] == "Are you still there?"
    assert _state(client, chat) == {"status": "active", "specialist": "Avery"}
    assert _chats(client, avery) == [("Mira Shah", False)]
    assert _state(client, jon)["status"] == "waiting"

    # Idle at 3 minutes: Avery's one slot is free, so the waiting customer is offered to her.
    clock.advance(minutes=1)
    live = client.get("/live", headers=avery).json()
    assert [(c["customer"], c["idle"]) for c in live["chats"]] == [("Mira Shah", True)]
    assert [offer["customer"] for offer in live["offers"]] == ["Jon Hale"]
    assert _state(client, chat) == {"status": "idle", "specialist": None}
    assert client.get("/chat", headers=chat).json()["status"] == "Are you still there?"
    assert client.post(f"/live/{held['id']}/messages", headers=avery, json={"text": "Hello?"}).status_code == 403
    assert client.post(f"/live/{held['id']}/resolve", headers=avery).status_code == 403

    clock.advance(minutes=11, seconds=59)
    assert _state(client, chat)["status"] == "idle"
    clock.advance(seconds=1)
    # Staff sign-ins last 15 minutes, so the staff sign in again.
    avery, lead = _avery(client), _staff(client, "lead@northstar.example", "northstar-lead")
    view = client.get("/chat", headers=chat).json()
    assert view["status"] == CLOSED
    assert view["messages"][-1] == {"role": "specialist", "name": "Avery", "text": ANSWER}
    assert _state(client, chat) is None
    assert client.get(f"/cases/{held['case_id']}", headers=lead).json()["status"] == "Resolved"
    assert _chats(client, avery) == []
    assert [e for e in _events() if e in ("live_chat_idle", "live_chat_closed")] == ["live_chat_idle", "live_chat_closed"]

    # Writing again starts a new case, as after a resolved live chat, and the agent answers it.
    after = _say(client, chat, "How long is the return window?")
    assert after["status"] == "" and after["messages"][-1]["role"] == "assistant"


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_the_clock_does_not_run_while_the_customer_waits_for_the_specialist(client, clock):
    chat, avery = _chat(client), _avery(client)
    client.post("/presence", headers=avery, json={"state": "available"})
    assert client.post("/chat/live", headers=chat).status_code == 200
    offer = client.get("/live", headers=avery).json()["offers"][0]["id"]
    client.post(f"/live/{offer}/accept", headers=avery)

    # Accepted, and the specialist has not written yet.
    clock.advance(minutes=10)
    assert client.get("/chat", headers=chat).json()["status"] == ""
    assert _chats(client, avery) == [("Mira Shah", False)]

    # The customer answered the specialist's last message, so the customer is the one waiting.
    client.post(f"/live/{offer}/messages", headers=avery, json={"text": "Hi Mira, how can I help?"})
    clock.advance(minutes=1)
    _say(client, chat, "My coat has a torn seam.")
    clock.advance(minutes=10)
    avery = _avery(client)
    assert client.get("/chat", headers=chat).json()["status"] == ""
    assert _state(client, chat) == {"status": "active", "specialist": "Avery"}
    assert _chats(client, avery) == [("Mira Shah", False)]
    assert "live_chat_idle" not in _events()


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_a_customer_back_from_idle_returns_to_the_same_specialist_when_she_has_a_slot(client, clock, monkeypatch):
    chat, avery = _chat(client), _avery(client)
    held = _answered(client, chat, avery)
    clock.advance(minutes=4)
    assert _chats(client, avery) == [("Mira Shah", True)]

    # The customer's message goes to the specialist. The agent stays quiet.
    monkeypatch.setattr(CaseStore, "ask", lambda *args, **kwargs: pytest.fail("the agent took a turn"))
    view = _say(client, chat, "Sorry, I stepped away. Can the refund go to my card?")
    monkeypatch.undo()
    assert view["status"] == ""
    assert view["messages"][-1] == {"role": "user", "text": "Sorry, I stepped away. Can the refund go to my card?"}
    assert _state(client, chat) == {"status": "active", "specialist": "Avery"}
    [back] = client.get("/live", headers=avery).json()["chats"]
    assert back["id"] == held["id"] and back["idle"] is False
    assert [m["text"] for m in back["messages"]][-2:] == [ANSWER, "Sorry, I stepped away. Can the refund go to my card?"]
    assert client.post(f"/live/{held['id']}/messages", headers=avery, json={"text": "Yes, it can."}).status_code == 200
    assert _events().count("live_chat_returned") == 1


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_a_customer_back_from_idle_goes_to_the_front_of_the_line_when_the_specialist_is_full(client, clock):
    chat, jon, third, avery = _chat(client, MIRA), _chat(client, JON), _chat(client, _third_customer()), _avery(client)
    _answered(client, chat, avery)
    _one_slot()

    # Mira goes quiet, and Jon, who keeps his chat open, takes Avery's only slot.
    clock.advance(minutes=1)
    client.post("/chat/live", headers=jon)
    clock.advance(minutes=1)
    assert _state(client, jon)["status"] == "waiting"
    clock.advance(minutes=1)
    [offer] = client.get("/live", headers=avery).json()["offers"]
    client.post(f"/live/{offer['id']}/accept", headers=avery)

    # An escalated request joins the line before Mira comes back. It would go ahead of any requested chat.
    clock.advance(minutes=1)
    with ConnectionPool(TEST_URL, min_size=1, max_size=2, kwargs={"row_factory": dict_row}) as pool:
        third_id = uuid.uuid5(uuid.NAMESPACE_URL, "quiet.customer@example.test")
        assert CaseStore(pool, clock, live_chats=True).request_live(third_id, reason="escalated")
    clock.advance(minutes=1)
    view = _say(client, chat, "I am back. Is the refund done?")
    assert view["messages"][-1] == {"role": "user", "text": "I am back. Is the refund done?"}
    assert view["status"].startswith("You are number 1 in line.")
    assert client.get("/chat", headers=third).json()["status"].startswith("You are number 2 in line.")
    assert _state(client, chat) == {"status": "waiting", "specialist": None}
    assert _chats(client, avery) == [("Jon Hale", False)]

    # Avery's slot frees up, and Mira is offered first, ahead of the escalated customer who joined earlier.
    client.post(f"/live/{offer['id']}/resolve", headers=avery)
    assert [o["customer"] for o in client.get("/live", headers=avery).json()["offers"]] == ["Mira Shah"]
    assert _state(client, third)["status"] == "waiting"


@pytest.mark.parametrize(
    "client",
    [{"live_agents_enabled": True, "quiet_nudge_minutes": 1, "quiet_idle_minutes": 5, "quiet_close_minutes": 10}],
    indirect=True,
)
def test_the_three_times_are_settings(client, clock):
    chat, avery = _chat(client), _avery(client)
    _answered(client, chat, avery)
    clock.advance(minutes=1)
    assert client.get("/chat", headers=chat).json()["status"] == "Are you still there?"
    clock.advance(minutes=3)
    assert _chats(client, avery) == [("Mira Shah", False)]
    clock.advance(minutes=1)
    assert _chats(client, avery) == [("Mira Shah", True)]
    clock.advance(minutes=4)
    assert _state(client, chat)["status"] == "idle"
    clock.advance(minutes=1)
    assert client.get("/chat", headers=chat).json()["status"] == CLOSED


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_many_reads_at_once_idle_a_chat_and_bring_the_customer_back_once(client, clock):
    chat, avery = _chat(client), _avery(client)
    held = _answered(client, chat, avery)
    clock.advance(minutes=3)
    with ConnectionPool(TEST_URL, min_size=1, max_size=8, kwargs={"row_factory": dict_row}) as pool:
        store = CaseStore(pool, clock, live_chats=True)

        def at_once(start: threading.Barrier) -> None:
            start.wait()
            store._quiet()

        for step in ("idle", "back"):
            if step == "back":
                with _db() as conn:
                    conn.execute(
                        "INSERT INTO case_messages (case_id, role, body, created_at) VALUES (%s, 'user', 'Still here.', %s)",
                        (held["case_id"], clock.now()),
                    )
            start = threading.Barrier(8)
            with ThreadPoolExecutor(max_workers=8) as workers:
                list(workers.map(lambda _: at_once(start), range(8)))
    assert _events().count("live_chat_idle") == 1
    assert _events().count("live_chat_returned") == 1
    assert _chats(client, avery) == [("Mira Shah", False)]


@pytest.mark.parametrize("client", LIVE, indirect=True)
def test_a_quiet_chat_with_a_waiting_proposal_goes_idle_and_closes_only_after_the_lead_decides(client, clock):
    chat, avery = _chat(client), _avery(client)
    client.post("/presence", headers=avery, json={"state": "available"})
    assert client.post("/chat/live", headers=chat).status_code == 200
    offer = client.get("/live", headers=avery).json()["offers"][0]["id"]
    client.post(f"/live/{offer}/accept", headers=avery)
    # The specialist's action turn is her last word, so the quiet clock starts from it.
    assert client.post(f"/live/{offer}/actions", headers=avery, json={"text": "Please refund order NS-1001."}).status_code == 200

    # Quiet for 15 minutes while the proposal waits: the slot is free, but the chat does not close.
    clock.advance(minutes=15)
    avery, lead = _avery(client), _staff(client, "lead@northstar.example", "northstar-lead")
    assert _state(client, chat) == {"status": "idle", "specialist": None}
    assert _chats(client, avery) == [("Mira Shah", True)]
    [proposal] = client.get("/approvals", headers=lead).json()
    assert proposal["order_id"] == "NS-1001"
    assert client.get(f"/cases/{proposal['case_id']}", headers=lead).json()["status"] == "Waiting for approval"
    assert "live_chat_closed" not in _events()

    # The lead decides, and the customer is still quiet, so the next read closes the live chat.
    assert client.post(f"/approvals/{proposal['case_id']}/approve", headers=lead).status_code == 200
    assert _state(client, chat) is None
    assert client.get(f"/cases/{proposal['case_id']}", headers=lead).json()["status"] == "Resolved"
    assert client.get("/chat", headers=chat).json()["status"].startswith("Our team approved your request.")
    assert _events().count("live_chat_closed") == 1
