"""Abstained handbook questions are listed for a lead with the weak sections retrieved (R19)."""

from northstar.retrieve import retrieved_answer


def _login(client, email: str, password: str) -> dict:
    token = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _ask_in_a_new_case(client, staff: dict, question: str, clock) -> None:
    client.post("/cases/current/messages", headers=staff, json={"question": question})
    client.post("/cases/current/resolve", headers=staff, json={"final_text": "Done."})
    clock.advance(seconds=1)
    client.post("/cases/current/new", headers=staff)


def test_an_abstain_keeps_the_weak_sections_it_retrieved(monkeypatch):
    monkeypatch.setenv("RETRIEVAL_SCORE_TAU", "1.5")
    draft = retrieved_answer("How long may apparel and footwear be returned?")
    assert draft.decision == "abstain"
    assert draft.citations == ()
    assert draft.retrieved and draft.retrieved[0][0] == "REF-CATEGORY"
    assert all(score < 1.5 for _, score in draft.retrieved)


def test_the_lead_sees_gaps_by_frequency_and_the_specialist_does_not(client, clock, monkeypatch):
    monkeypatch.setenv("RETRIEVAL_SCORE_TAU", "1.5")
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    lead = _login(client, "lead@northstar.example", "northstar-lead")
    _ask_in_a_new_case(client, specialist, "How long may apparel and footwear be returned?", clock)
    _ask_in_a_new_case(client, specialist, "What are the support hours on weekdays?", clock)
    _ask_in_a_new_case(client, specialist, "how long may apparel and footwear be returned", clock)
    _ask_in_a_new_case(client, specialist, "How much is the silk hat?", clock)  # a catalog abstain is not a handbook gap

    gaps = client.get("/gaps", headers=lead).json()
    assert [gap["count"] for gap in gaps] == [2, 1]
    assert gaps[0]["question"] == "How long may apparel and footwear be returned?"
    assert gaps[0]["sections"][0]["section_id"] == "REF-CATEGORY"
    assert client.get("/gaps", headers=specialist).status_code == 403
