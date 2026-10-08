def _token(client) -> str:
    return client.post(
        "/auth/login",
        json={"email": "specialist@northstar.example", "password": "northstar-specialist"},
    ).json()["access_token"]


def _ask(client, token: str, question: str):
    return client.post(
        "/cases/current/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": question},
    )


def test_a_resolved_case_keeps_both_texts_and_refuses_another_message(client):
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}
    draft = _ask(client, token, "How long is the return window for apparel?").json()
    draft_body = draft["messages"][-1]["body"]
    closed = client.post(
        "/cases/current/resolve",
        headers=headers,
        json={"final_text": "Apparel can be returned for 30 days after delivery."},
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "Resolved"
    assert closed.json()["draft_text"] == draft_body
    assert closed.json()["final_text"] == "Apparel can be returned for 30 days after delivery."

    refused = _ask(client, token, "What about electronics?")
    assert refused.status_code == 409
    again = client.get("/cases/current", headers=headers).json()
    assert [message["body"] for message in again["messages"]] == [
        message["body"] for message in draft["messages"]
    ]
    assert again["draft_text"] == draft_body
    assert again["final_text"] == "Apparel can be returned for 30 days after delivery."


def test_an_escalated_case_refuses_another_message(client):
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}
    _ask(client, token, "How long is the return window for apparel?")
    closed = client.post(
        "/cases/current/escalate",
        headers=headers,
        json={"final_text": "Sending this to a person."},
    )
    assert closed.json()["status"] == "Escalated"
    assert closed.json()["final_text"] == "Sending this to a person."
    assert closed.json()["draft_text"]
    assert _ask(client, token, "Please just refund it.").status_code == 409
