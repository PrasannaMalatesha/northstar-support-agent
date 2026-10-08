"""Slice 2 labeled desk cases run through the API, the way the console calls it."""

import pytest

from evals.labeled import SLICE2_CASES, slice2_problems


def _login(client, email: str, password: str) -> dict:
    token = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_slice2_cases_cite_the_registry():
    assert slice2_problems() == []


@pytest.mark.parametrize("case", SLICE2_CASES, ids=[case["id"] for case in SLICE2_CASES])
def test_slice2_case(client, case):
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    lead = _login(client, "lead@northstar.example", "northstar-lead")
    if case["customer"]:
        client.post("/cases/current/customer", headers=specialist, json={"query": case["customer"]})
    body = client.post("/cases/current/messages", headers=specialist, json={"question": case["question"]}).json()
    draft = body["messages"][-1]
    assert draft["decision"] == case["decision"], draft
    assert all(section in draft["citations"] for section in case["sections"]), draft
    assert body["status"] == case["status"]
    assert body["ticket_id"] is None
    waiting = client.get("/approvals", headers=lead).json()
    assert [row["action"] for row in waiting] == ([case["action"]] if case["action"] else [])
