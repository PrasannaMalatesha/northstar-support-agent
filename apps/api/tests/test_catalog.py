def _ask(client, question: str) -> str:
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
    return response.json()["messages"][-1]["body"]


def test_a_known_item_uses_only_the_catalog_row(client):
    body = _ask(client, "How much is the wool coat?")
    assert body == (
        "Wool coat. Category: apparel and footwear. "
        "Price: $128.00. Sizes: S, M, L. In stock: yes. Final sale: no."
    )
    assert "left" not in body


def test_an_unknown_item_and_a_missing_field_abstain(client):
    unknown = _ask(client, "Is the oak sofa in stock?")
    assert unknown == "I don't have that item in the catalog."
    missing = _ask(client, "What material is the wool coat?")
    assert missing == "The catalog row does not have that field."
    earbuds = _ask(client, "Are the trail earbuds in stock?")
    assert "In stock: no." in earbuds
    assert "0" not in earbuds.split("In stock: ")[1]


def test_do_you_sell_asks_the_catalog_and_a_policy_question_still_reaches_the_handbook(client):
    # R21: what Northstar sells comes from catalog rows; an unknown item abstains.
    assert _ask(client, "Do you sell surfboard wax?") == "I don't have that item in the catalog."
    assert _ask(client, "Do you carry the wool coat?").startswith("Wool coat. Category: apparel and footwear.")
    assert "(GC-TERMS)" in _ask(client, "Do you have gift cards that expire?")


def test_a_complaint_that_names_an_item_is_not_answered_with_its_catalog_row(client):
    body = _ask(client, "The rain jacket I bought is the wrong color.")
    assert "Price:" not in body


def test_a_catalog_question_still_gets_the_catalog_row(client):
    assert "Price: $96.00" in _ask(client, "Is the rain jacket in stock?")
