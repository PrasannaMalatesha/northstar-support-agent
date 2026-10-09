"""The escalations inbox (R38): escalated cases with their handoffs, picked up by one specialist.

A specialist's reply to a chat case reaches that customer's chat, as written and screened.
"""

import os
import threading
import uuid

import psycopg
from northstar.cases import AlreadyPickedUp, CaseStore
from northstar.clock import SystemClock
from northstar.identity.postgres import PostgresIdentityStore
from northstar.identity.service import staff_id_for
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://northstar:northstar@localhost:5433/northstar_test")
MIRA = {"order_id": "NS-1001", "email": "mira.shah@northstar.example"}
CHARGEBACK = "I will open a chargeback with my bank."


def _staff(client, email, password) -> dict:
    token = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _specialist(client) -> dict:
    return _staff(client, "specialist@northstar.example", "northstar-specialist")


def _lead(client) -> dict:
    return _staff(client, "lead@northstar.example", "northstar-lead")


def _add_specialists(*emails: str) -> None:
    from northstar.identity.service import hash_password

    pool = ConnectionPool(_URL, min_size=1, max_size=1, kwargs={"row_factory": dict_row}, open=True)
    try:
        for email in emails:
            PostgresIdentityStore(pool).upsert_staff(
                staff_id_for(email), email, "Sam Ortiz", hash_password("northstar-second"), "specialist"
            )
    finally:
        pool.close()


def _chat(client) -> dict:
    started = client.post("/chat/start", json=MIRA)
    assert started.status_code == 200, started.text
    return {"Authorization": f"Bearer {started.json()['chat_token']}"}


def _say(client, chat, question: str) -> dict:
    sent = client.post("/chat/messages", headers=chat, json={"question": question})
    assert sent.status_code == 200, sent.text
    return sent.json()


def _escalated_chat(client) -> tuple[dict, str]:
    chat = _chat(client)
    _say(client, chat, CHARGEBACK)
    items = client.get("/inbox", headers=_lead(client)).json()
    return chat, next(item["case_id"] for item in items if item["source"] == "chat")


def _events() -> list[str]:
    with psycopg.connect(_URL) as conn:
        return [row[0] for row in conn.execute("SELECT event FROM audit_log ORDER BY id")]


def test_an_escalated_desk_case_and_chat_case_appear_with_their_handoffs(client, clock):
    specialist = _specialist(client)
    desk = client.post(
        "/cases/current/messages",
        headers=specialist,
        json={"question": "A chargeback is already filed. Refund the order so I will drop it."},
    ).json()
    assert desk["status"] == "Escalated"
    clock.advance(minutes=5)
    _say(client, _chat(client), CHARGEBACK)

    items = client.get("/inbox", headers=_lead(client)).json()
    assert [item["source"] for item in items] == ["desk", "chat"]
    assert all("Asked:" in item["handoff"] and "ESC-LEGAL" in item["handoff"] for item in items)
    assert items[1]["customer"] == "Mira Shah"
    assert all(item["assigned_to"] is None and item["replies"] == [] for item in items)
    # A specialist sees the same unpicked items. A customer token never reaches the inbox.
    assert [item["case_id"] for item in client.get("/inbox", headers=specialist).json()] == [item["case_id"] for item in items]
    assert client.get("/inbox", headers=_chat(client)).status_code == 401


def test_a_picked_up_case_is_theirs_and_no_other_specialist_can_take_it(client):
    _add_specialists("sam.ortiz@northstar.example")
    _, case_id = _escalated_chat(client)
    avery, sam, lead = _specialist(client), _staff(client, "sam.ortiz@northstar.example", "northstar-second"), _lead(client)

    assert client.post(f"/inbox/{case_id}/pick-up", headers=avery).status_code == 200
    assert client.post(f"/inbox/{case_id}/pick-up", headers=avery).status_code == 200
    taken = client.post(f"/inbox/{case_id}/pick-up", headers=sam)
    assert taken.status_code == 409
    assert "Another specialist" in taken.json()["detail"]

    mine = client.get("/inbox", headers=avery).json()
    assert [(item["assigned_to"], item["mine"]) for item in mine] == [("Avery Cole", True)]
    assert client.get("/inbox", headers=sam).json() == []
    assert [(item["assigned_to"], item["mine"]) for item in client.get("/inbox", headers=lead).json()] == [("Avery Cole", False)]
    # Leads approve; they do not pick up. Only escalated cases are in the inbox.
    assert client.post(f"/inbox/{case_id}/pick-up", headers=lead).status_code == 403
    open_case = client.get("/cases/current", headers=sam).json()["id"]
    assert client.post(f"/inbox/{open_case}/pick-up", headers=sam).status_code == 404
    assert client.post("/inbox/not-a-case/pick-up", headers=sam).status_code == 404
    assert _events().count("escalation_pick_up") == 2


def test_concurrent_pick_ups_have_exactly_one_winner(client):
    emails = [f"specialist{n}@northstar.example" for n in range(6)]
    _add_specialists(*emails)
    _, case_id = _escalated_chat(client)
    start, won, lost = threading.Barrier(len(emails)), [], []
    with ConnectionPool(_URL, min_size=6, max_size=6, kwargs={"row_factory": dict_row}) as pool:
        store = CaseStore(pool, SystemClock())

        def try_pick_up(email: str) -> None:
            start.wait()
            try:
                store.pick_up(staff_id_for(email), uuid.UUID(case_id))
                won.append(email)
            except AlreadyPickedUp:
                lost.append(email)

        threads = [threading.Thread(target=try_pick_up, args=(email,)) for email in emails]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    assert len(won) == 1 and len(lost) == len(emails) - 1


def test_a_reply_reaches_the_customer_chat_as_written_and_is_audited(client):
    chat, case_id = _escalated_chat(client)
    avery = _specialist(client)
    client.post(f"/inbox/{case_id}/pick-up", headers=avery)
    text = "Hi Mira, I checked order NS-1001 with our payments team. Call me back on 512-555-0199."
    assert client.post(f"/inbox/{case_id}/reply", headers=avery, json={"text": text}).status_code == 200

    view = client.get("/chat", headers=chat).json()
    assert set(view) == {"status", "messages"}
    assert view["messages"][-1] == {
        "role": "specialist",
        "name": "Avery",
        "text": "Hi Mira, I checked order NS-1001 with our payments team. Call me back on [phone].",
    }
    assert view["messages"][-2]["text"] == "A specialist will follow up with you about this."
    assert _events()[-1] == "escalation_reply"
    assert client.get("/inbox", headers=avery).json()[0]["replies"][0]["text"].endswith("[phone].")


def test_only_the_specialist_who_picked_up_a_chat_case_replies(client):
    _add_specialists("sam.ortiz@northstar.example")
    _, case_id = _escalated_chat(client)
    avery, sam = _specialist(client), _staff(client, "sam.ortiz@northstar.example", "northstar-second")
    reply = {"text": "We are on it."}
    assert client.post(f"/inbox/{case_id}/reply", headers=avery, json=reply).status_code == 403
    client.post(f"/inbox/{case_id}/pick-up", headers=avery)
    assert client.post(f"/inbox/{case_id}/reply", headers=sam, json=reply).status_code == 403
    assert client.post(f"/inbox/{case_id}/reply", headers=avery, json={"text": "   "}).status_code == 422
    assert client.post(f"/inbox/{case_id}/reply", headers=_lead(client), json=reply).status_code == 403

    # A desk case has no customer chat to reply into.
    desk = client.post(
        "/cases/current/messages",
        headers=sam,
        json={"question": "A chargeback is already filed. Refund the order so I will drop it."},
    ).json()
    client.post(f"/inbox/{desk['id']}/pick-up", headers=sam)
    assert client.post(f"/inbox/{desk['id']}/reply", headers=sam, json=reply).status_code == 403
    assert "escalation_reply" not in _events()


def test_a_reply_keeps_the_case_escalated_and_reaches_a_customer_on_a_new_chat_case(client, clock):
    chat, case_id = _escalated_chat(client)
    # The customer writes again before the reply, which starts a new chat case (#121).
    # The clock moves, so the new case is the latest by time and not by a random id.
    clock.advance(minutes=5)
    _say(client, chat, "How long may apparel and footwear be returned?")
    avery = _specialist(client)
    client.post(f"/inbox/{case_id}/pick-up", headers=avery)
    client.post(f"/inbox/{case_id}/reply", headers=avery, json={"text": "Your bank dispute is noted. No refund is promised."})

    escalated = client.get(f"/cases/{case_id}", headers=_lead(client)).json()
    assert escalated["status"] == "Escalated"
    assert [m["role"] for m in escalated["messages"]] == ["user", "assistant", "specialist"]

    view = client.get("/chat", headers=chat).json()
    assert view["status"] == ""
    assert [m["role"] for m in view["messages"]] == ["user", "assistant", "specialist"]
    assert view["messages"][-1]["text"] == "Your bank dispute is noted. No refund is promised."
    assert "REF-CATEGORY" in view["messages"][1]["text"]

    # The next customer message is an agent turn on the new case. The escalated case takes none (R30).
    after = _say(client, chat, "Thanks. How long do I have to return shoes?")
    assert [m["role"] for m in after["messages"]] == ["user", "assistant", "specialist", "user", "assistant"]
    escalated = client.get(f"/cases/{case_id}", headers=_lead(client)).json()
    assert escalated["status"] == "Escalated"
    assert [m["role"] for m in escalated["messages"]] == ["user", "assistant", "specialist"]


def test_the_chat_tells_the_customer_to_come_back_for_the_reply(client):
    chat, _ = _escalated_chat(client)
    status = client.get("/chat", headers=chat).json()["status"]
    assert status.startswith("A specialist will follow up with you.")
    assert "same order id and email" in status
