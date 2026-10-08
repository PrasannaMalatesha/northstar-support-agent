"""Every escalated case carries a handoff packet that stands alone (R17)."""


def _login(client, email: str, password: str) -> dict:
    token = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _fields(packet: str) -> dict[str, str]:
    return dict(line.split(": ", 1) for line in packet.splitlines())


def test_a_legal_escalation_names_order_sections_tries_and_owner(client):
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    client.post("/cases/current/customer", headers=specialist, json={"query": "mira.shah@northstar.example"})
    client.post("/cases/current/messages", headers=specialist, json={"question": "Please refund order NS-1003."})
    # The deny proposal waits; a lead rejects it so the case can take the next turn.
    lead = _login(client, "lead@northstar.example", "northstar-lead")
    case_id = client.get("/cases/current", headers=specialist).json()["id"]
    client.post(f"/approvals/{case_id}/reject", headers=lead, json={"reason": "Already refunded."})
    body = client.post(
        "/cases/current/messages",
        headers=specialist,
        json={"question": "My lawyer will file a chargeback on NS-1003. Email me at mira@example.com."},
    ).json()
    assert body["status"] == "Escalated"
    packet = _fields(body["handoff"])
    assert packet["Order"] == "NS-1003"
    assert "ESC-LEGAL" in packet["Sections read"]
    assert packet["Tried"] == "deny (REF-DENY)"
    assert packet["Owner"] == "legal"
    assert "mira@example.com" not in body["handoff"]


def test_a_policy_conflict_goes_to_the_policy_owner(client):
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    client.post("/cases/current/customer", headers=specialist, json={"query": "mira.shah@northstar.example"})
    body = client.post(
        "/cases/current/messages",
        headers=specialist,
        json={"question": "The website said I have 60 days to return order NS-1001."},
    ).json()
    packet = _fields(body["handoff"])
    assert packet["Owner"] == "policy"
    assert packet["Tried"] == "Nothing yet."


def test_a_specialist_escalation_carries_a_packet_with_their_note(client):
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    client.post("/cases/current/customer", headers=specialist, json={"query": "mira.shah@northstar.example"})
    client.post("/cases/current/messages", headers=specialist, json={"question": "Where is order NS-1001?"})
    body = client.post(
        "/cases/current/escalate",
        headers=specialist,
        json={"final_text": "Customer disputes the delivery date on the record."},
    ).json()
    assert body["status"] == "Escalated"
    packet = _fields(body["handoff"])
    assert packet["Order"] == "NS-1001"
    assert packet["Tried"] == "order"
    assert packet["Missing"] == "Specialist note: Customer disputes the delivery date on the record."
    assert packet["Owner"] == "support lead"
