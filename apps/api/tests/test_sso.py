"""Staff sign in with Google (issue #78). A local RSA key stands in for Google's signing key."""

import os
import time

import jwt
import psycopg
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

import northstar.identity.service as service

CLIENT = "northstar-test.apps.googleusercontent.com"
_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://northstar:northstar@localhost:5433/northstar_test")
_GOOGLE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER = rsa.generate_private_key(public_exponent=65537, key_size=2048)
SSO_ON = pytest.mark.parametrize("client", [{"google_client_id": CLIENT}], indirect=True)


@pytest.fixture(autouse=True)
def google_keys(monkeypatch):
    monkeypatch.setattr(service, "_google_key", lambda token: _GOOGLE.public_key())


def _id_token(key=_GOOGLE, **overrides) -> str:
    now = int(time.time())
    claims = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT,
        "sub": "1234567890",
        "email": "lead@northstar.example",
        "email_verified": True,
        "iat": now,
        "exp": now + 600,
    }
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm="RS256")


def _events() -> list[str]:
    with psycopg.connect(_URL) as conn:
        return [row[0] for row in conn.execute("SELECT event FROM audit_log ORDER BY id")]


@SSO_ON
def test_a_verified_google_account_gets_the_role_from_the_staff_record(client):
    signed = client.post("/auth/sso", json={"id_token": _id_token(role="specialist")})
    assert signed.status_code == 200, signed.text
    assert signed.json()["role"] == "lead"  # the staff table decides, not a claim in the token
    headers = {"Authorization": f"Bearer {signed.json()['access_token']}"}
    assert client.get("/approvals", headers=headers).status_code == 200
    assert "sso_login_success" in _events()


@SSO_ON
@pytest.mark.parametrize(
    "token",
    [
        _id_token(email="stranger@example.com"),
        _id_token(email_verified=False),
        _id_token(aud="someone-else.apps.googleusercontent.com"),
        _id_token(iss="https://evil.example"),
        _id_token(exp=int(time.time()) - 3600),
        _id_token(key=_OTHER),
        _id_token(email="chat@northstar.example"),  # disabled account
    ],
    ids=["unknown-email", "unverified-email", "wrong-audience", "wrong-issuer", "expired", "wrong-signature", "disabled"],
)
def test_anything_short_of_a_valid_token_for_an_active_staff_member_is_refused(client, token):
    assert client.post("/auth/sso", json={"id_token": token}).status_code == 401
    assert _events()[-1] == "sso_login_failure"


@pytest.mark.parametrize("client", [{"google_client_id": ""}], indirect=True)
def test_sso_is_off_without_a_client_id(client):
    assert client.post("/auth/sso", json={"id_token": _id_token()}).status_code == 404


@SSO_ON
def test_a_disabled_staff_member_loses_the_sso_session(client):
    signed = client.post("/auth/sso", json={"id_token": _id_token()}).json()
    headers = {"Authorization": f"Bearer {signed['access_token']}"}
    with psycopg.connect(_URL) as conn:
        conn.execute("UPDATE staff_users SET disabled_at = now() WHERE email = 'lead@northstar.example'")
    assert client.get("/approvals", headers=headers).status_code == 401
    assert client.post("/auth/sso", json={"id_token": _id_token()}).status_code == 401


@SSO_ON
def test_an_sso_logout_is_audited(client):
    signed = client.post("/auth/sso", json={"id_token": _id_token()}).json()
    assert client.post("/auth/logout", json={"refresh_token": signed["refresh_token"]}).status_code == 200
    assert _events()[-1] == "logout"
