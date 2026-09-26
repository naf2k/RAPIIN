"""Tests for notifications, search filters and supervisor profile."""
import time

from .test_auth import _register_user


def _login(client, email, password="Password123!"):
    return client.post("/api/auth/login", json={"email": email, "password": password}).json()["token"]


def test_task_completion_creates_notifications(client, monkeypatch):
    """A completed task creates a USER notification (and supervisor on failure)."""
    import rapiin.ai.provider as provider_mod

    from .test_chat import DummyProvider

    monkeypatch.setattr(provider_mod, "get_provider", lambda: DummyProvider())

    _register_user(client)
    token = _login(client, "andi@example.com")
    conv = client.post("/api/user/conversations", json={}, headers={"Authorization": f"Bearer {token}"}).json()
    resp = client.post(
        f"/api/user/conversations/{conv['conversation_id']}/messages",
        json={"content": "Ringkas pekerjaan saya."},
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    # Wait for the async worker to finish.
    deadline = time.time() + 15
    while time.time() < deadline:
        task = client.get(f"/api/user/tasks/{resp['task_id']}", headers={"Authorization": f"Bearer {token}"}).json()
        if task["status"] == "COMPLETED":
            break
        time.sleep(0.3)

    notifs = client.get("/api/user/notifications", headers={"Authorization": f"Bearer {token}"}).json()
    assert len(notifs) >= 1
    assert notifs[0]["type"] == "success"
    unread = client.get("/api/user/notifications/unread-count", headers={"Authorization": f"Bearer {token}"}).json()
    assert unread["count"] >= 1


def test_supervisor_search_tasks_and_employees(client, monkeypatch):
    """Supervisor can search tasks/employees with q param."""
    _register_user(client, "andi@example.com")
    _register_user(client, "budi@example.com")
    sup_token = _login(client, "supervisor@rapiin.example.com", "Supervisor123!")

    emps = client.get("/api/supervisor/employees?q=andi", headers={"Authorization": f"Bearer {sup_token}"}).json()
    assert len(emps) >= 1
    assert "andi" in emps[0]["email"].lower()

    emps_all = client.get("/api/supervisor/employees", headers={"Authorization": f"Bearer {sup_token}"}).json()
    assert len(emps_all) >= 2


def test_supervisor_profile_and_accounts(client):
    sup_token = _login(client, "supervisor@rapiin.example.com", "Supervisor123!")

    profile = client.get("/api/supervisor/profile", headers={"Authorization": f"Bearer {sup_token}"}).json()
    assert profile["role"] == "SUPERVISOR"

    patch = client.patch(
        "/api/supervisor/profile",
        json={"name": "Supervisor Utama"},
        headers={"Authorization": f"Bearer {sup_token}"},
    )
    assert patch.status_code == 200

    accounts = client.get("/api/supervisor/accounts", headers={"Authorization": f"Bearer {sup_token}"}).json()
    assert accounts["max"] == 2
    assert accounts["count"] >= 1


def test_supervisor_create_employee(client):
    sup_token = _login(client, "supervisor@rapiin.example.com", "Supervisor123!")
    resp = client.post(
        "/api/supervisor/employees",
        json={"name": "Karyawan Baru", "email": "baru@example.com", "password": "Password123!"},
        headers={"Authorization": f"Bearer {sup_token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["user_id"]

    # Can log in as the new employee
    token = _login(client, "baru@example.com")
    assert token


def test_user_settings_and_profile(client):
    _register_user(client)
    token = _login(client, "andi@example.com")

    put = client.put("/api/user/settings", json={"key": "startup_mode", "value": "auto"}, headers={"Authorization": f"Bearer {token}"})
    assert put.status_code == 200

    got = client.get("/api/user/settings", headers={"Authorization": f"Bearer {token}"}).json()
    assert got.get("startup_mode") == "auto"

    patch = client.patch("/api/user/profile", json={"name": "Andi Baru"}, headers={"Authorization": f"Bearer {token}"})
    assert patch.status_code == 200
    prof = client.get("/api/user/profile", headers={"Authorization": f"Bearer {token}"}).json()
    assert prof["name"] == "Andi Baru"
