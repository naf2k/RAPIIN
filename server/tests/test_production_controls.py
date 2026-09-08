from .test_auth import _register_user


def _login(client, email, password="Password123!"):
    return client.post("/api/auth/login", json={"email": email, "password": password}).json()["token"]


def test_supervisor_can_configure_safe_policy_but_not_auto_delete(client):
    supervisor = _login(client, "supervisor@beresin.example.com", "Supervisor123!")
    headers = {"Authorization": f"Bearer {supervisor}"}
    updated = client.put("/api/supervisor/policies/file_move", json={"approval_kind": "SUPERVISOR", "bulk_threshold": 5}, headers=headers)
    assert updated.status_code == 200
    policies = client.get("/api/supervisor/policies", headers=headers).json()
    move = next(p for p in policies if p["tool_name"] == "file_move")
    assert move["approval_kind"] == "SUPERVISOR"
    rejected = client.put("/api/supervisor/policies/file_delete", json={"approval_kind": "AUTO", "bulk_threshold": 20}, headers=headers)
    assert rejected.status_code == 422


def test_permission_engine_loads_database_policy(client):
    from beresin.database import db_session, utcnow_iso
    from beresin.permissions import PermissionEngine
    with db_session() as conn:
        conn.execute("INSERT INTO action_policies VALUES (?, ?, ?, ?, ?)", ("file_move", "SUPERVISOR", 5, 1, utcnow_iso()))
        engine = PermissionEngine.from_db(conn)
        assert engine.action_approval_kind("file_move", count=1) == "SUPERVISOR"


def test_user_can_cancel_pending_task(client):
    _register_user(client, "cancel@example.com")
    token = _login(client, "cancel@example.com")
    from beresin.database import db_session
    from beresin.tasks import create_task
    with db_session() as conn:
        user_id = conn.execute("SELECT id FROM users WHERE email = 'cancel@example.com'").fetchone()["id"]
        task_id = create_task(conn, user_id=user_id, device_id=None, type="scan")
    response = client.post(f"/api/user/tasks/{task_id}/cancel", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    task = client.get(f"/api/user/tasks/{task_id}", headers={"Authorization": f"Bearer {token}"}).json()
    assert task["status"] == "CANCELLED"
    assert task["cancel_requested"] == 1


def test_tool_gateway_exposes_all_prd_parser_and_verification_contracts():
    from beresin.tools.registry import get_tools_schema
    names = {tool["function"]["name"] for tool in get_tools_schema()}
    assert {"pdf_parser", "spreadsheet_parser", "verification"} <= names


def test_agent_poll_receives_desired_startup_mode_and_device_health(client):
    body = client.post("/api/auth/register", json={
        "email": "settings-agent@example.com", "name": "Agent", "password": "Password123!",
        "device_name": "Laptop", "os": "Test", "agent_version": "1.0",
    }).json()
    headers = {"Authorization": f"Bearer {body['token']}"}
    client.put("/api/user/settings", json={"key": "startup_mode", "value": "auto"}, headers=headers)
    poll = client.post("/api/agent/poll", json={"device_id": body["device"]["id"], "device_key": body["device"]["device_key"]}).json()
    assert poll["settings"]["startup_mode"] == "auto"
    devices = client.get("/api/user/devices", headers=headers).json()
    assert devices[0]["connection_health"] == "HEALTHY"
    assert devices[0]["heartbeat_age_seconds"] is not None


def test_readiness_and_security_headers(client):
    response = client.get("/ready", headers={"X-Request-ID": "test-request-id"})
    assert response.status_code == 200
    assert response.json()["database"] == "ok"
    assert response.headers["x-request-id"] == "test-request-id"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["permissions-policy"].startswith("camera=()")


def test_internal_metrics_requires_dedicated_monitoring_token(client, monkeypatch):
    from beresin.config import settings
    monkeypatch.setattr(settings, "beresin_monitoring_token", "monitor-token-abcdefghijklmnopqrstuvwxyz")
    assert client.get("/internal/metrics").status_code == 403
    response = client.get("/internal/metrics", headers={"Authorization": "Bearer monitor-token-abcdefghijklmnopqrstuvwxyz"})
    assert response.status_code == 200
    assert "beresin_queue_length" in response.text


def test_login_rate_limit_and_logout_revokes_token(client):
    registration = client.post("/api/auth/register", json={
        "email": "rate-limit@example.com", "name": "Rate Limit", "password": "Password123!",
        "device_name": "PC", "os": "Test", "agent_version": "1.0",
    })
    assert registration.status_code == 200
    for _ in range(5):
        response = client.post("/api/auth/login", json={"email": "rate-limit@example.com", "password": "WrongPassword1"})
        assert response.status_code == 401
    blocked = client.post("/api/auth/login", json={"email": "rate-limit@example.com", "password": "Password123!"})
    assert blocked.status_code == 429

    token = registration.json()["token"]
    assert client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert client.get("/api/user/tasks", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_public_registration_can_be_disabled(client, monkeypatch):
    from beresin.config import settings
    monkeypatch.setattr(settings, "beresin_allow_public_registration", False)
    response = client.post("/api/auth/register", json={
        "email": "closed@example.com", "name": "Closed", "password": "Password123!",
        "device_name": "PC", "os": "Test", "agent_version": "1.0",
    })
    assert response.status_code == 403


def test_supervisor_account_limit_is_enforced(client):
    token = _login(client, "supervisor@beresin.example.com", "Supervisor123!")
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post("/api/supervisor/accounts", json={"name": "Supervisor Dua", "email": "sup2@example.com", "password": "StrongPassword123!"}, headers=headers)
    assert created.status_code == 200
    third = client.post("/api/supervisor/accounts", json={"name": "Supervisor Tiga", "email": "sup3@example.com", "password": "StrongPassword123!"}, headers=headers)
    assert third.status_code == 409
