def _token(client) -> str:
    return client.post(
        "/auth/login",
        json={"email": "specialist@northstar.example", "password": "northstar-specialist"},
    ).json()["access_token"]


def test_email_or_phone_binds_the_customer_and_a_miss_stays_unbound(client):
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}

    by_email = client.post(
        "/cases/current/customer",
        headers=headers,
        json={"query": "Mira.Shah@northstar.example"},
    )
    assert by_email.status_code == 200
    assert by_email.json()["customer"]["name"] == "Mira Shah"

    by_phone = client.post(
        "/cases/current/customer",
        headers=headers,
        json={"query": "(512) 555-0198"},
    )
    assert by_phone.json()["customer"]["name"] == "Jon Hale"

    missed = client.post(
        "/cases/current/customer",
        headers=headers,
        json={"query": "nobody@northstar.example"},
    )
    assert missed.json()["customer"]["name"] == "Jon Hale"
    assert client.post("/customers", headers=headers, json={"name": "New"}).status_code == 404

    handbook = client.post(
        "/cases/current/messages",
        headers=headers,
        json={"question": "How long is the return window for apparel?"},
    )
    assert "REF-CATEGORY" in handbook.json()["messages"][-1]["citations"]


def test_an_order_question_on_an_unbound_case_reads_no_order(client):
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}
    asked = client.post(
        "/cases/current/messages",
        headers=headers,
        json={"question": "Where is order 1001?"},
    )
    draft = asked.json()["messages"][-1]
    assert draft["body"] == "Pick a customer first. No order was read."
    assert draft["citations"] == []
    assert asked.json()["customer"] is None
