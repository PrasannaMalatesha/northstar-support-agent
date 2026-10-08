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


def test_the_shown_draft_redacts_email_phone_and_card(client):
    body = _ask(
        client,
        "How long is the return window for apparel? "
        "Email mira.shah@northstar.example or call 512-555-0199. "
        "Card 4111111111111111.",
    )
    shown = " ".join(message["body"] for message in body["messages"])
    assert "mira.shah@northstar.example" not in shown
    assert "512-555-0199" not in shown
    assert "4111111111111111" not in shown
    assert "[email]" in shown
    assert "[phone]" in shown
    assert "1111" in shown


def test_a_secret_stops_the_turn(client):
    secret = "sk-test-abcdef123456"
    body = _ask(client, f"What is the return window? {secret}")
    draft = body["messages"][-1]
    assert draft["citations"] == []
    assert draft["body"] == "This message contains a secret and was stopped."
    assert secret not in " ".join(message["body"] for message in body["messages"])


def test_an_id_with_digit_runs_is_not_mistaken_for_a_card():
    from northstar.privacy import screen

    ticket = "b4ae3b77-5903-4050-888e-c7d1a0590353"
    assert screen(f"Ticket: {ticket}.") == f"Ticket: {ticket}."
    assert screen("Card 4111 1111 1111 1111.") == "Card ************1111."
    assert screen("Card 4111-1111-1111-1111") == "Card ************1111"
