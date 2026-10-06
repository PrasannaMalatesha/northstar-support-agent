def _open(client, question: str) -> dict:
    token = client.post(
        "/auth/login",
        json={"email": "specialist@northstar.example", "password": "northstar-specialist"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.post(
        "/cases/current/customer",
        headers=headers,
        json={"query": "mira.shah@northstar.example"},
    )
    response = client.post(
        "/cases/current/messages",
        headers=headers,
        json={"question": question},
    )
    assert response.status_code == 200
    return response.json()


def test_a_refund_inside_the_window_waits_and_creates_no_ticket(client):
    body = _open(client, "Please refund order NS-1001.")
    assert body["status"] == "Waiting for approval"
    assert body["action"] == "approve_refund"
    assert body["refund_amount_cents"] == 12800
    assert body["refund_amount_cents"] <= 12800
    assert "REF-ELIGIBILITY" in body["policy_citations"]
    assert "REF-CATEGORY" in body["policy_citations"]
    assert body["ticket_id"] is None
    assert "12800" in body["messages"][-1]["body"]


def test_a_used_item_is_half_credit_rounded_down(client):
    body = _open(client, "The wool coat was used. Refund order NS-1001.")
    assert body["action"] == "partial_credit"
    assert body["refund_amount_cents"] == 6400
    assert "REF-PARTIAL" in body["policy_citations"]


def test_an_already_refunded_line_is_denied(client):
    body = _open(client, "Please refund order NS-1003.")
    assert body["action"] == "deny"
    assert body["refund_amount_cents"] == 0
    assert body["policy_citations"] == ["REF-DENY"]
    assert "2000" not in body["messages"][-1]["body"]


def test_a_refund_without_an_order_id_does_not_guess_an_amount(client):
    token = client.post(
        "/auth/login",
        json={"email": "specialist@northstar.example", "password": "northstar-specialist"},
    ).json()["access_token"]
    response = client.post(
        "/cases/current/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "Please refund this."},
    ).json()
    assert response["status"] == "Open"
    assert response["refund_amount_cents"] is None
    assert response["messages"][-1]["body"] == "Which order id? No amount is proposed."
