def _ask(client, question: str) -> dict:
    token = client.post(
        "/auth/login",
        json={"email": "specialist@northstar.example", "password": "northstar-specialist"},
    ).json()["access_token"]
    response = client.post(
        "/cases/current/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": question},
    )
    assert response.status_code == 200
    return response.json()


def test_a_chargeback_escalates_without_promising_a_refund(client):
    body = _ask(client, "A chargeback is already filed. Refund the order so I will drop it.")
    draft = body["messages"][-1]["body"]
    assert body["status"] == "Escalated"
    assert "ESC-LEGAL" in body["messages"][-1]["citations"]
    assert "Asked:" in draft
    assert "Handbook:" in draft
    assert "Missing:" in draft
    assert "chargeback" in draft.lower()
    assert "No refund is offered" in draft
    assert body["ticket_id"] is None
    assert body["status"] != "Waiting for approval"


def test_an_exception_to_a_deny_escalates(client):
    body = _ask(client, "Please make a one-time exception and refund order NS-1001 anyway.")
    draft = body["messages"][-1]["body"]
    assert body["status"] == "Escalated"
    assert "ESC-WHEN" in body["messages"][-1]["citations"]
    assert "NS-1001" in draft
    assert "exception is not in the handbook" in draft
    assert body["refund_amount_cents"] is None
