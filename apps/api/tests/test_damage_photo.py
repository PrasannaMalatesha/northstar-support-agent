"""REF-DAMAGED, and a damaged-item photo that informs the lead but never decides (issue #80).

A stand-in describer replaces the vision model, so no key or network is used.
"""

import base64

import psycopg
import pytest

import northstar.cases as cases
from evals.experiments import photo_url
from evals.labeled import PHOTO_CASES
from northstar.photo import Photo

_URL = "postgresql://northstar:northstar@localhost:5433/northstar_test"
_VERDICTS = {
    "lamp-cracked.png": Photo(True, True, "The shade is cracked."),
    "lamp-intact.png": Photo(True, False, "The lamp looks whole."),
    "not-the-item.png": Photo(False, False, "A drawing of a house and a tree."),
}


def _login(client, email, password):
    token = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _bound(client):
    specialist = _login(client, "specialist@northstar.example", "northstar-specialist")
    client.post("/cases/current/customer", headers=specialist, json={"query": "mira.shah@northstar.example"})
    return specialist


@pytest.fixture()
def described(monkeypatch):
    by_url = {photo_url(name): verdict for name, verdict in _VERDICTS.items()}
    monkeypatch.setattr(cases, "describe", lambda url, note: by_url[url])


def test_damage_within_14_days_is_a_full_refund_under_ref_damaged(client):
    body = client.post(
        "/cases/current/messages", headers=_bound(client), json={"question": "The desk lamp on order NS-1011 arrived damaged."}
    ).json()
    draft = body["messages"][-1]
    assert draft["decision"] == "approve_refund"
    assert draft["citations"] == ["REF-DAMAGED"]
    assert "4200 cents" in draft["body"]
    assert body["status"] == "Waiting for approval"


def test_damage_after_14_days_falls_back_to_the_return_window(client, clock):
    clock.advance(days=20)  # 26 days after delivery: past REF-DAMAGED, inside the 30-day home window
    body = client.post(
        "/cases/current/messages", headers=_bound(client), json={"question": "The desk lamp on order NS-1011 arrived damaged."}
    ).json()
    assert body["messages"][-1]["citations"] == ["REF-ELIGIBILITY", "REF-CATEGORY"]


@pytest.mark.parametrize("case", PHOTO_CASES, ids=[case["id"] for case in PHOTO_CASES])
def test_the_photo_verdict_reaches_the_draft_and_the_lead_but_the_words_decide(client, described, case):
    body = client.post(
        "/cases/current/messages",
        headers=_bound(client),
        json={"question": case["question"], "photo": photo_url(case["photo"])},
    ).json()
    draft = body["messages"][-1]
    assert draft["decision"] == case["decision"]
    assert draft["citations"] == list(case["sections"])
    assert f"Photo: {case['photo_verdict']}." in draft["body"]
    assert body["messages"][-2]["body"].endswith("[Photo attached]")
    lead = _login(client, "lead@northstar.example", "northstar-lead")
    waiting = client.get("/approvals", headers=lead).json()
    assert any(f"Photo: {case['photo_verdict']}." in item["details"] for item in waiting)


def test_a_photo_alone_proposes_nothing(client, described):
    body = client.post(
        "/cases/current/messages",
        headers=_bound(client),
        json={"question": "How long may home and kitchen items be returned?", "photo": photo_url("lamp-cracked.png")},
    ).json()
    assert body["messages"][-1]["decision"] == "answer"
    assert body["status"] == "Open"
    assert "Photo: visible damage." in body["messages"][-1]["body"]


def test_without_a_vision_model_the_photo_is_noted_and_nothing_breaks(client):
    body = client.post(
        "/cases/current/messages",
        headers=_bound(client),
        json={"question": "The desk lamp on order NS-1011 arrived damaged.", "photo": photo_url("lamp-cracked.png")},
    ).json()
    assert body["messages"][-1]["decision"] == "approve_refund"
    assert "Photo: attached, but it could not be described." in body["messages"][-1]["body"]


def test_a_bad_photo_is_refused_before_the_desk_runs(client):
    specialist = _bound(client)
    text = "data:text/plain;base64," + base64.b64encode(b"hello").decode()
    assert client.post("/cases/current/messages", headers=specialist, json={"question": "Damaged.", "photo": text}).status_code == 422
    huge = "data:image/png;base64," + base64.b64encode(b"0" * (4 * 1024 * 1024 + 1)).decode()
    assert client.post("/cases/current/messages", headers=specialist, json={"question": "Damaged.", "photo": huge}).status_code == 422
    assert client.get("/cases/current", headers=specialist).json()["messages"] == []


def test_a_real_sized_photo_fits_but_other_routes_stay_small(client, described, monkeypatch):
    # About 3 MB of image bytes, as a phone photo would be. The describer is stood in.
    monkeypatch.setattr(cases, "describe", lambda url, note: Photo(True, True, "The shade is cracked."))
    big = "data:image/png;base64," + base64.b64encode(b"0" * (3 * 1024 * 1024)).decode()
    sent = client.post(
        "/cases/current/messages",
        headers=_bound(client),
        json={"question": "The desk lamp on order NS-1011 arrived damaged.", "photo": big},
    )
    assert sent.status_code == 200
    assert client.post("/auth/login", json={"email": "x" * 20_000, "password": "y"}).status_code == 413


def test_the_image_itself_is_never_stored(client, described):
    client.post(
        "/cases/current/messages",
        headers=_bound(client),
        json={"question": "The desk lamp on order NS-1011 arrived damaged.", "photo": photo_url("lamp-cracked.png")},
    )
    with psycopg.connect(_URL) as conn:
        stored = conn.execute(
            "SELECT count(*) FROM case_messages WHERE body LIKE '%base64%' OR body LIKE '%iVBOR%'"
        ).fetchone()[0]
        details = conn.execute("SELECT count(*) FROM cases WHERE proposal_details LIKE '%base64%'").fetchone()[0]
    assert stored == 0 and details == 0
