"""Chat limits are per customer, with a total for all chat customers (issue #134).

The counts live in Postgres, so a restarted API (a new store) sees the same counts.
"""

from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import SECRET, TEST_URL
from fastapi.testclient import TestClient
from northstar.cases import REQUEST_LIMIT_TEXT
from northstar.privacy import SECRET_REPLY

from northstar_api.main import create_app
from northstar_api.settings import Settings

MIRA = {"order_id": "NS-1001", "email": "mira.shah@northstar.example"}
JON = {"order_id": "NS-1002", "email": "jon.hale@northstar.example"}


def _chat(client, body) -> dict:
    started = client.post("/chat/start", json=body)
    assert started.status_code == 200, started.text
    return {"Authorization": f"Bearer {started.json()['chat_token']}"}


def _say(client, headers, question: str = "What is your favorite color?") -> str:
    sent = client.post("/chat/messages", headers=headers, json={"question": question})
    assert sent.status_code == 200, sent.text
    return sent.json()["messages"][-1]["text"]


def test_a_customer_at_ten_turns_gets_the_limit_message_and_another_customer_still_chats(client):
    mira = _chat(client, MIRA)
    replies = [_say(client, mira) for _ in range(10)]
    assert REQUEST_LIMIT_TEXT not in replies
    assert _say(client, mira) == REQUEST_LIMIT_TEXT
    assert len(client.get("/chat", headers=mira).json()["messages"]) == 22

    assert _say(client, _chat(client, JON)) != REQUEST_LIMIT_TEXT


@pytest.mark.parametrize("client", [{"chat_turns_per_customer": 2, "chat_turns_per_day": 3}], indirect=True)
def test_the_total_for_all_chat_customers_stops_further_turns(client):
    mira, jon = _chat(client, MIRA), _chat(client, JON)
    assert _say(client, mira) != REQUEST_LIMIT_TEXT
    assert _say(client, mira) != REQUEST_LIMIT_TEXT
    # Mira's own limit. A refused turn is not counted in the total.
    assert _say(client, mira) == REQUEST_LIMIT_TEXT
    assert _say(client, jon) != REQUEST_LIMIT_TEXT
    # Jon has used one of his two turns, but all chat customers have used three.
    assert _say(client, jon) == REQUEST_LIMIT_TEXT


@pytest.mark.parametrize("client", [{"chat_turns_per_customer": 5}], indirect=True)
def test_turns_sent_at_once_are_counted_exactly(client):
    mira = _chat(client, MIRA)
    # One turn first: the process opens its preference store on first use, and that open is not thread safe.
    assert _say(client, mira, "my api_key = abc123") == SECRET_REPLY
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda _: _say(client, mira, "my api_key = abc123"), range(12)))
    replies = [m["text"] for m in client.get("/chat", headers=mira).json()["messages"] if m["role"] != "user"]
    assert replies.count(SECRET_REPLY) == 5
    assert replies.count(REQUEST_LIMIT_TEXT) == 8


@pytest.mark.parametrize("client", [{"chat_turns_per_customer": 1, "request_limit": 1}], indirect=True)
def test_limits_hold_after_the_api_restarts(client, clock):
    mira = _chat(client, MIRA)
    assert _say(client, mira) != REQUEST_LIMIT_TEXT
    login = {"email": "specialist@northstar.example", "password": "northstar-specialist"}
    staff = {"Authorization": f"Bearer {client.post('/auth/login', json=login).json()['access_token']}"}
    asked = client.post("/cases/current/messages", headers=staff, json={"question": "What is your favorite color?"})
    assert asked.json()["messages"][-1]["body"] != REQUEST_LIMIT_TEXT

    # A new app with its own pool and store, as after a restart or in a second server process.
    settings = Settings(database_url=TEST_URL, token_secret=SECRET, chat_turns_per_customer=1, request_limit=1)
    with TestClient(create_app(settings=settings, clock=clock)) as restarted:
        assert _say(restarted, _chat(restarted, MIRA)) == REQUEST_LIMIT_TEXT
        staff = {"Authorization": f"Bearer {restarted.post('/auth/login', json=login).json()['access_token']}"}
        asked = restarted.post("/cases/current/messages", headers=staff, json={"question": "How long is the return window?"})
        assert asked.json()["messages"][-1]["body"] == REQUEST_LIMIT_TEXT
        assert _say(restarted, _chat(restarted, JON)) != REQUEST_LIMIT_TEXT
