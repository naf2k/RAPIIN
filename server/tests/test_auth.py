def _register_user(client, email="andi@example.com"):
    return client.post(
        "/api/auth/register",
        json={
            "email": email,
            "name": "Andi Test",
            "password": "Password123!",
            "device_name": "PC-ANDI-TEST",
            "os": "Windows 11",
            "agent_version": "1.0.0",
        },
    )


def test_register_and_login(client):
    reg = _register_user(client)
    assert reg.status_code == 200, reg.text
    body = reg.json()
    assert body["token"]
    assert body["device"]["device_name"] == "PC-ANDI-TEST"

    login = client.post(
        "/api/auth/login",
        json={"email": "andi@example.com", "password": "Password123!"},
    )
    assert login.status_code == 200
    assert login.json()["role"] == "USER"


def test_login_wrong_password(client):
    _register_user(client)
    resp = client.post(
        "/api/auth/login",
        json={"email": "andi@example.com", "password": "salah"},
    )
    assert resp.status_code == 401


def test_supervisor_seeded_and_login(client):
    login = client.post(
        "/api/auth/login",
        json={"email": "supervisor@rapiin.example.com", "password": "Supervisor123!"},
    )
    assert login.status_code == 200, login.text
    assert login.json()["role"] == "SUPERVISOR"


def test_user_cannot_access_supervisor_api(client):
    _register_user(client)
    token = client.post(
        "/api/auth/login",
        json={"email": "andi@example.com", "password": "Password123!"},
    ).json()["token"]
    resp = client.get("/api/supervisor/overview", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_supervisor_overview(client):
    login = client.post(
        "/api/auth/login",
        json={"email": "supervisor@rapiin.example.com", "password": "Supervisor123!"},
    )
    token = login.json()["token"]
    resp = client.get("/api/supervisor/overview", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert "active_users" in resp.json()
