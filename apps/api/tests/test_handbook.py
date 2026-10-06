def test_a_covered_question_is_cited_and_survives_a_reread(client):
    token = client.post(
        "/auth/login",
        json={"email": "specialist@northstar.example", "password": "northstar-specialist"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    asked = client.post(
        "/cases/current/messages",
        headers=headers,
        json={"question": "How long is the return window for apparel?"},
    )
    assert asked.status_code == 200
    draft = asked.json()["messages"][-1]
    assert draft["decision"] == "answer"
    assert "REF-CATEGORY" in draft["citations"]
    assert "REF-CATEGORY" in draft["body"]

    again = client.get("/cases/current", headers=headers)
    assert again.json()["messages"][-1]["body"] == draft["body"]


def test_the_turn_lists_steps_then_marks_each_citation_strong_or_weak(client):
    token = client.post(
        "/auth/login",
        json={"email": "specialist@northstar.example", "password": "northstar-specialist"},
    ).json()["access_token"]
    asked = client.post(
        "/cases/current/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "How long is the return window for apparel?"},
    )
    draft = asked.json()["messages"][-1]
    assert draft["steps"] == [
        "Classifying the question",
        "Reading the handbook",
    ]
    assert 1 <= len(draft["citations"]) <= 4
    assert set(draft["match"]) == set(draft["citations"])
    assert set(draft["match"].values()) <= {"strong", "weak"}
    assert "strong" in draft["match"].values()


def test_an_uncovered_question_abstains_and_names_what_to_ask(client):
    token = client.post(
        "/auth/login",
        json={"email": "specialist@northstar.example", "password": "northstar-specialist"},
    ).json()["access_token"]
    asked = client.post(
        "/cases/current/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "What is your favorite color?"},
    )
    draft = asked.json()["messages"][-1]
    assert draft["decision"] == "abstain"
    assert draft["citations"] == []
    assert "returns" in draft["body"]
