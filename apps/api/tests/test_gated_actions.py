"""A proposal carries its action, and each proposal gets its own ticket."""

from northstar.actions import ACTIONS, PROPOSALS, gated


def _login(client, email: str, password: str) -> dict:
    token = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_the_router_reads_one_table_of_gated_actions():
    assert gated("Please refund order NS-1001.").kind == "refund"
    assert gated("Store credit for NS-1001, please.").kind == "refund"
    assert gated("Where is order NS-1001?") is None
    assert {"approve_refund", "partial_credit", "deny"} <= PROPOSALS
    assert len({action.kind for action in ACTIONS}) == len(ACTIONS)


def test_a_second_proposal_on_the_same_case_gets_its_own_ticket(client):
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    lead = _login(client, "lead@northstar.example", "northstar-lead")
    client.post("/cases/current/customer", headers=specialist, json={"query": "mira.shah@northstar.example"})
    first = client.post("/cases/current/messages", headers=specialist, json={"question": "Please refund order NS-1001."}).json()
    assert first["action"] == "approve_refund"
    ticket_one = client.post(f"/approvals/{first['id']}/approve", headers=lead).json()["ticket_id"]
    again = client.post(f"/approvals/{first['id']}/approve", headers=lead).json()["ticket_id"]
    assert again == ticket_one

    second = client.post("/cases/current/messages", headers=specialist, json={"question": "Exchange order NS-1001 for size L."}).json()
    assert second["status"] == "Waiting for approval"
    assert second["action"] == "exchange"
    assert second["ticket_id"] is None
    ticket_two = client.post(f"/approvals/{second['id']}/approve", headers=lead).json()["ticket_id"]
    assert ticket_two != ticket_one

    waiting = client.get("/approvals", headers=lead).json()
    assert waiting == []


def test_the_waiting_list_shows_action_details_and_amount(client):
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    lead = _login(client, "lead@northstar.example", "northstar-lead")
    client.post("/cases/current/customer", headers=specialist, json={"query": "mira.shah@northstar.example"})
    client.post("/cases/current/messages", headers=specialist, json={"question": "Please refund order NS-1001."})
    row = client.get("/approvals", headers=lead).json()[0]
    assert row["action"] == "approve_refund"
    assert row["amount_cents"] == 12800
    assert row["details"] == ""
    assert row["order_id"] == "NS-1001"


def test_a_leak_or_a_split_seam_is_a_defect_and_a_lost_gift_card_is_not_a_lost_package():
    assert gated("The rain jacket leaks at the seams.").kind == "warranty_claim"
    assert gated("The seams on my coat came apart.").kind == "warranty_claim"
    lost_card = gated("A customer lost the physical gift card she was given. Can we replace it?")
    assert lost_card is None or lost_card.kind != "shipment"
    assert gated("My gift card was lost in the move.") is None or gated("My gift card was lost in the move.").kind != "shipment"
    assert gated("Order NS-1009 is lost.").kind == "shipment"
    assert gated("Order NS-1009 never arrived.").kind == "shipment"
