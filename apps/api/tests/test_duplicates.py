"""One open or completed ticket per order and action family (R15)."""


def _login(client, email: str, password: str) -> dict:
    token = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _next_case(client, staff: dict) -> None:
    client.post("/cases/current/resolve", headers=staff, json={"final_text": "Done."})
    client.post("/cases/current/new", headers=staff)
    client.post("/cases/current/customer", headers=staff, json={"query": "mira.shah@northstar.example"})


def _ask(client, staff: dict, question: str) -> dict:
    return client.post("/cases/current/messages", headers=staff, json={"question": question}).json()


def test_a_completed_refund_ticket_blocks_a_second_refund(client, clock):
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    lead = _login(client, "lead@northstar.example", "northstar-lead")
    client.post("/cases/current/customer", headers=specialist, json={"query": "mira.shah@northstar.example"})
    first = _ask(client, specialist, "Please refund order NS-1001.")
    ticket = client.post(f"/approvals/{first['id']}/approve", headers=lead).json()["ticket_id"]

    clock.advance(seconds=1)
    _next_case(client, specialist)
    again = _ask(client, specialist, "Please refund order NS-1001.")
    draft = again["messages"][-1]
    assert draft["decision"] == "duplicate"
    assert ticket in draft["body"]
    assert again["status"] == "Open"
    assert client.get("/approvals", headers=lead).json() == []


def test_a_completed_cancel_blocks_a_second_cancel_but_not_another_action(client, clock):
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    lead = _login(client, "lead@northstar.example", "northstar-lead")
    client.post("/cases/current/customer", headers=specialist, json={"query": "mira.shah@northstar.example"})
    first = _ask(client, specialist, "Cancel order NS-1004.")
    ticket = client.post(f"/approvals/{first['id']}/approve", headers=lead).json()["ticket_id"]

    clock.advance(seconds=1)
    _next_case(client, specialist)
    again = _ask(client, specialist, "Cancel order NS-1004.")
    assert again["messages"][-1]["decision"] == "duplicate"
    assert ticket in again["messages"][-1]["body"]

    # Nothing else changes on a cancelled order (ORD-CANCEL), so another family is checked the other way round.
    cancelled = _ask(client, specialist, "Change the address on order NS-1004 to 12 Oak St, Austin TX 78701.")
    assert cancelled["messages"][-1]["citations"] == ["ORD-CANCEL"]


def test_a_completed_address_change_blocks_a_second_one_but_not_a_cancel(client, clock):
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    lead = _login(client, "lead@northstar.example", "northstar-lead")
    client.post("/cases/current/customer", headers=specialist, json={"query": "mira.shah@northstar.example"})
    first = _ask(client, specialist, "Change the address on order NS-1004 to 12 Oak St, Austin TX 78701.")
    ticket = client.post(f"/approvals/{first['id']}/approve", headers=lead).json()["ticket_id"]

    clock.advance(seconds=1)
    _next_case(client, specialist)
    again = _ask(client, specialist, "Change the address on order NS-1004 to 40 Elm Ave, Round Rock TX 78664.")
    assert again["messages"][-1]["decision"] == "duplicate"
    assert ticket in again["messages"][-1]["body"]

    other = _ask(client, specialist, "Cancel order NS-1004.")
    assert other["action"] == "cancel"
    assert other["status"] == "Waiting for approval"


def test_a_proposal_waiting_on_another_case_blocks_the_same_one(client):
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    lead = _login(client, "lead@northstar.example", "northstar-lead")
    client.post("/cases/current/customer", headers=lead, json={"query": "mira.shah@northstar.example"})
    waiting = _ask(client, lead, "Cancel order NS-1004.")
    assert waiting["status"] == "Waiting for approval"

    client.post("/cases/current/customer", headers=specialist, json={"query": "mira.shah@northstar.example"})
    second = _ask(client, specialist, "Cancel order NS-1004.")
    assert second["messages"][-1]["decision"] == "duplicate"
    assert waiting["id"] in second["messages"][-1]["body"]
    assert second["status"] == "Open"
