def _login(client, email: str, password: str) -> str:
    return client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_history_lists_five_past_cases_and_hides_transcripts(client, clock):
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    lead = _login(client, "lead@northstar.example", "northstar-lead")
    headers = _headers(specialist)
    closed_ids = []
    for index in range(6):
        if index:
            clock.advance(seconds=1)
            opened = client.post("/cases/current/new", headers=headers)
            assert opened.status_code == 200
            assert opened.json()["id"] != closed_ids[-1]
            assert opened.json()["history"] == []
        client.post(
            "/cases/current/customer",
            headers=headers,
            json={"query": "mira.shah@northstar.example"},
        )
        if index == 5:
            case_id = client.post(
                "/cases/current/messages",
                headers=headers,
                json={"question": "Please refund order NS-1003."},
            ).json()["id"]
            rejected = client.post(
                f"/approvals/{case_id}/reject",
                headers=_headers(lead),
                json={"reason": "Already refunded."},
            )
            assert rejected.status_code == 200, rejected.text
            assert client.get("/cases/current", headers=headers).json()["status"] == "Open"
        current = client.get("/cases/current", headers=headers).json()
        closed_ids.append(current["id"])
        closed = client.post(
            "/cases/current/resolve",
            headers=headers,
            json={"final_text": f"Closed case {index}."},
        )
        assert closed.status_code == 200
    clock.advance(seconds=1)
    opened = client.post("/cases/current/new", headers=headers)
    assert opened.json()["history"] == []
    client.post(
        "/cases/current/customer",
        headers=headers,
        json={"query": "mira.shah@northstar.example"},
    )
    history = client.get("/cases/current", headers=headers).json()["history"]
    assert len(history) == 5
    assert len(closed_ids) == 6
    assert any(item["refunded_lines"] == ["refunded"] for item in history)
    assert "Closed case" not in str(history)
    for item in history:
        assert set(item) == {"id", "status", "outcome", "refunded_lines"}
        assert item["outcome"]
    assert client.patch("/cases/current/history", headers=headers, json={"id": closed_ids[0]}).status_code == 404
