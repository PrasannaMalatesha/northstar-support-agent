"""Edge cases from round 3 of the conversation checks (EDGECASES.md)."""


def _login(client, email: str, password: str) -> dict:
    token = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _desk(client) -> dict:
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    client.post("/cases/current/customer", headers=specialist, json={"query": "mira.shah@northstar.example"})
    return specialist


def test_a_message_of_only_spaces_is_refused_and_nothing_is_saved(client):
    specialist = _desk(client)
    assert client.post("/cases/current/messages", headers=specialist, json={"question": "   "}).status_code == 422
    assert client.get("/cases/current", headers=specialist).json()["messages"] == []
    chat = {"Authorization": "Bearer " + client.post("/chat/start", json={"order_id": "NS-1001", "email": "mira.shah@northstar.example"}).json()["chat_token"]}
    assert client.post("/chat/messages", headers=chat, json={"question": "  \n "}).status_code == 422


def test_an_order_id_without_the_dash_is_the_same_order(client):
    specialist = _desk(client)
    body = client.post("/cases/current/messages", headers=specialist, json={"question": "Refund order NS1006."}).json()
    assert body["messages"][-1]["decision"] == "approve_refund" and "9600 cents" in body["messages"][-1]["body"]
    assert client.post("/chat/start", json={"order_id": "ns1006", "email": "mira.shah@northstar.example"}).status_code == 200


def test_order_ids_are_written_back_one_way():
    from northstar.actions import order_id, order_ids

    assert order_id("refund ns1006 please") == "NS-1006"
    assert order_ids("Refund NS-1001 and ns1004, then NS-1001 again") == ["NS-1001", "NS-1004"]
    assert order_id("call 512-555-1006") is None


def test_guessing_many_emails_for_one_order_locks_that_order(client):
    for i in range(5):
        assert client.post("/chat/start", json={"order_id": "NS-1006", "email": f"guess{i}@example.com"}).status_code == 401
    assert client.post("/chat/start", json={"order_id": "NS-1006", "email": "another@example.com"}).status_code == 423
    # Another order is not locked by it.
    assert client.post("/chat/start", json={"order_id": "NS-1001", "email": "mira.shah@northstar.example"}).status_code == 200


def test_an_exchange_to_the_size_already_owned_says_so(client):
    specialist = _desk(client)
    body = client.post("/cases/current/messages", headers=specialist, json={"question": "Exchange order NS-1001 for size M."}).json()
    assert "already size M" in body["messages"][-1]["body"]
