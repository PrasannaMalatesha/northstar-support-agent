def test_specialist_can_sign_in_and_read_only_name_and_role(client):
    signed_in = client.post(
        "/auth/login",
        json={
            "email": "specialist@northstar.example",
            "password": "northstar-specialist",
        },
    )
    assert signed_in.status_code == 200
    body = signed_in.json()
    assert body["role"] == "specialist"
    assert body["name"] == "Avery Cole"
    assert "access_token" in body
    assert "database_url" not in body
    assert "password" not in body

    me = client.get("/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json() == {"name": "Avery Cole", "role": "specialist"}


def test_lead_can_sign_in(client):
    signed_in = client.post(
        "/auth/login",
        json={"email": "lead@northstar.example", "password": "northstar-lead"},
    )
    assert signed_in.status_code == 200
    assert signed_in.json()["role"] == "lead"


def test_wrong_password_does_not_open_a_session(client):
    signed_in = client.post(
        "/auth/login",
        json={"email": "specialist@northstar.example", "password": "nope"},
    )
    assert signed_in.status_code == 401
    assert client.get("/me").status_code == 401


def test_there_is_no_public_sign_up(client):
    assert client.post("/auth/register", json={"email": "a@b.c", "password": "x"}).status_code == 404


def test_logout_ends_the_session(client):
    signed_in = client.post(
        "/auth/login",
        json={
            "email": "specialist@northstar.example",
            "password": "northstar-specialist",
        },
    ).json()
    logged_out = client.post("/auth/logout", json={"refresh_token": signed_in["refresh_token"]})
    assert logged_out.status_code == 200
    assert (
        client.get(
            "/me",
            headers={"Authorization": f"Bearer {signed_in['access_token']}"},
        ).status_code
        == 401
    )
    assert (
        client.post("/auth/refresh", json={"refresh_token": signed_in["refresh_token"]}).status_code
        == 401
    )


def test_refresh_rotates_and_the_old_token_dies(client):
    signed_in = client.post(
        "/auth/login",
        json={
            "email": "specialist@northstar.example",
            "password": "northstar-specialist",
        },
    ).json()
    refreshed = client.post("/auth/refresh", json={"refresh_token": signed_in["refresh_token"]})
    assert refreshed.status_code == 200
    assert (
        client.post("/auth/refresh", json={"refresh_token": signed_in["refresh_token"]}).status_code
        == 401
    )
    me = client.get(
        "/me",
        headers={"Authorization": f"Bearer {refreshed.json()['access_token']}"},
    )
    assert me.status_code == 200


def test_five_failures_lock_the_login_until_the_window_passes(client, clock):
    for _ in range(5):
        response = client.post(
            "/auth/login",
            json={"email": "specialist@northstar.example", "password": "nope"},
        )
    assert response.status_code == 423
    assert "locked" in response.json()["detail"].lower()

    during_lock = client.post(
        "/auth/login",
        json={
            "email": "specialist@northstar.example",
            "password": "northstar-specialist",
        },
    )
    assert during_lock.status_code == 423

    clock.advance(minutes=16)
    after = client.post(
        "/auth/login",
        json={
            "email": "specialist@northstar.example",
            "password": "northstar-specialist",
        },
    )
    assert after.status_code == 200


def test_a_client_role_header_does_not_change_the_staff_role(client):
    signed_in = client.post(
        "/auth/login",
        json={
            "email": "specialist@northstar.example",
            "password": "northstar-specialist",
        },
    ).json()
    me = client.get(
        "/me",
        headers={
            "Authorization": f"Bearer {signed_in['access_token']}",
            "X-Role": "lead",
        },
    )
    assert me.json()["role"] == "specialist"
