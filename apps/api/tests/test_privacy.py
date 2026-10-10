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


def test_the_published_support_address_is_shown_and_a_customer_address_is_not():
    from northstar.privacy import screen

    assert screen("Customers reach Northstar at help@northstar.example.") == "Customers reach Northstar at help@northstar.example."
    assert screen("Customers reach Northstar at HELP@northstar.example.") == "Customers reach Northstar at HELP@northstar.example."
    # Same domain, but a customer: still masked.
    assert screen("Bound to mira.shah@northstar.example.") == "Bound to [email]."
    assert screen("Write to ana@example.com.") == "Write to [email]."


def test_every_address_the_handbook_publishes_is_on_the_list():
    import re

    from northstar.handbook import policy_dir
    from northstar.privacy import PUBLISHED_EMAILS

    found = {
        address.lower()
        for page in policy_dir().rglob("*.md")
        for address in re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", page.read_text())
    }
    assert found and found <= PUBLISHED_EMAILS


def test_the_contact_answer_keeps_the_support_address(client):
    body = _ask(client, "What email should a customer use to contact support?")
    assert "help@northstar.example" in body["messages"][-1]["body"]


def test_the_agent_email_filter_keeps_the_published_address():
    # Redacting it from the desk's answer made the model call the desk again (a slow turn).
    from northstar.privacy import detector

    find = detector("email")
    assert find("Customers reach Northstar at help@northstar.example.") == []
    assert [hit["value"] for hit in find("Bound to mira.shah@northstar.example.")] == ["mira.shah@northstar.example"]
