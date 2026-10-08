"""A warranty claim is drafted for a person to submit. The draft never says it is approved."""


def _login(client, email: str, password: str) -> dict:
    token = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_a_covered_defect_drafts_a_claim_that_waits_for_a_lead(client):
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    lead = _login(client, "lead@northstar.example", "northstar-lead")
    client.post("/cases/current/customer", headers=specialist, json={"query": "mira.shah@northstar.example"})
    body = client.post(
        "/cases/current/messages",
        headers=specialist,
        json={"question": "The desk speaker on order NS-1007 stopped working."},
    ).json()
    draft = body["messages"][-1]["body"]
    assert body["action"] == "warranty_claim"
    assert "approved" not in draft.lower()
    assert "2027-08-16" in draft
    assert body["proposal_details"].startswith("Desk speaker: ")
    ticket = client.post(f"/approvals/{body['id']}/approve", headers=lead).json()["ticket_id"]
    assert ticket
