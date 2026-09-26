"""Hardening tests: provider failure, incremental indexing, metrics."""
import time

import pytest

from .test_auth import _register_user


class FailingProvider:
    """Provider that always raises (simulates AI provider being down)."""

    def chat(self, messages, tools=None, max_tokens=None):
        from rapiin.ai.provider import AIProviderError

        raise AIProviderError("Penyedia AI tidak tersedia.")

    def tools_schema(self):
        return []

    def tool_result_message(self, call_id, content, name=""):
        return {"role": "tool", "tool_call_id": call_id, "content": content}


def _login(client, email):
    return client.post(
        "/api/auth/login", json={"email": email, "password": "Password123!"}
    ).json()["token"]


def test_provider_down_marks_task_failed(client, monkeypatch):
    """When the AI provider is down, the task fails gracefully with a message."""
    import rapiin.ai.provider as provider_mod

    monkeypatch.setattr(provider_mod, "get_provider", lambda: FailingProvider())

    _register_user(client)
    token = _login(client, "andi@example.com")
    conv = client.post("/api/user/conversations", json={}, headers={"Authorization": f"Bearer {token}"}).json()
    resp = client.post(
        f"/api/user/conversations/{conv['conversation_id']}/messages",
        json={"content": "Halo?"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert resp["status"] == "PROCESSING"

    # Worker fails the task.
    deadline = time.time() + 15
    while time.time() < deadline:
        task = client.get(f"/api/user/tasks/{resp['task_id']}", headers={"Authorization": f"Bearer {token}"}).json()
        if task["status"] == "FAILED":
            break
        time.sleep(0.3)
    assert task["status"] == "FAILED"
    assert task["error"]


def test_blocked_tool_event_is_not_marked_completed(client, monkeypatch):
    import rapiin.worker as worker
    from rapiin.database import db_session
    from rapiin.tasks import create_task

    registration = _register_user(client, "blocked@example.com").json()
    with db_session() as conn:
        conversation_id = conn.execute(
            "INSERT INTO conversations(user_id,title,created_at,updated_at) VALUES(?, 'test', datetime('now'), datetime('now'))",
            (registration["user_id"],),
        ).lastrowid
        task_id = create_task(conn, user_id=registration["user_id"], device_id=None, type="chat", status="RUNNING")

    class BlockedCore:
        def __init__(self, _provider): pass
        def run_user_conversation(self, *_args, **_kwargs):
            return {"final_response": "Tidak dapat dijalankan.", "tool_events": [{"tool": "filesystem_scanner", "status": "BLOCKED", "error": "Agent offline"}]}

    monkeypatch.setattr("rapiin.agent.core.HermesCore", BlockedCore)
    monkeypatch.setattr("rapiin.ai.provider.get_provider", lambda: object())
    worker._run_task(user_id=registration["user_id"], conversation_id=conversation_id, task_id=task_id, device_id=None)
    with db_session() as conn:
        task = conn.execute("SELECT status,error FROM tasks WHERE id=?", (task_id,)).fetchone()
    assert task["status"] == "FAILED"
    assert task["error"] == "Agent offline"


def test_incremental_index_skips_unchanged(client):
    """Second index run skips files whose size+mtime did not change."""

    from rapiin.permissions import sandbox_root

    _register_user(client)
    token = _login(client, "andi@example.com")

    # Create files inside the sandbox.
    root = sandbox_root()
    d = root / ".rapiin_index_test"
    d.mkdir(exist_ok=True)
    for i in range(3):
        (d / f"f{i}.txt").write_text(f"konten {i}")

    from rapiin.database import db_session
    from rapiin.tools.registry import execute_tool

    with db_session() as conn:
        user_id = conn.execute("SELECT id FROM users WHERE email = 'andi@example.com'").fetchone()["id"]
        r1 = execute_tool(conn, user_id=user_id, task_id=None, device_id=None, name="semantic_indexer", arguments={"path": str(d)})
        assert r1["indexed"] == 3

    with db_session() as conn:
        r2 = execute_tool(conn, user_id=user_id, task_id=None, device_id=None, name="semantic_indexer", arguments={"path": str(d)})
        assert r2["indexed"] == 0
        assert r2["unchanged_skipped"] == 3

    # Change one file -> only that file is re-indexed.
    (d / "f0.txt").write_text("konten berubah")
    with db_session() as conn:
        r3 = execute_tool(conn, user_id=user_id, task_id=None, device_id=None, name="semantic_indexer", arguments={"path": str(d)})
        assert r3["indexed"] == 1

    import shutil

    shutil.rmtree(d, ignore_errors=True)


def test_supervisor_metrics_endpoint(client):
    _register_user(client)
    sup = client.post(
        "/api/auth/login", json={"email": "supervisor@rapiin.example.com", "password": "Supervisor123!"}
    ).json()
    resp = client.get("/api/supervisor/metrics", headers={"Authorization": f"Bearer {sup['token']}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "success_rate" in data
    assert "online_devices" in data
    assert "queue_length" in data


def test_production_config_rejects_default_secrets():
    from rapiin.config import Settings
    unsafe = Settings(rapiin_env="production")
    with pytest.raises(RuntimeError, match="tidak aman"):
        unsafe.validate_for_startup()


def test_production_config_accepts_https_and_strong_secrets():
    from rapiin.config import Settings
    safe = Settings(
        rapiin_env="production",
        rapiin_secret_key="a-unique-long-random-secret-value",
        rapiin_init_supervisor_email="ops@rapiin.example.id",
        rapiin_init_supervisor_password="A-unique-password-123!",
        rapiin_allowed_origins="https://rapiin.example.com",
        rapiin_monitoring_token="monitoring-token-with-at-least-32-characters",
        rapiin_allow_public_registration=False,
        rapiin_embedded_queue_worker=False,
    )
    safe.validate_for_startup()
    assert safe.allowed_origins == ["https://rapiin.example.com"]


def test_production_operations_config_requires_bounded_runtime_and_secure_telegram():
    from rapiin.config import Settings
    base = dict(
        rapiin_env="production", rapiin_secret_key="a-unique-long-random-secret-value",
        rapiin_init_supervisor_email="ops@rapiin.example.id",
        rapiin_init_supervisor_password="A-unique-password-123!",
        rapiin_allowed_origins="https://rapiin.example.com",
        rapiin_monitoring_token="monitoring-token-with-at-least-32-characters",
        rapiin_allow_public_registration=False,
        rapiin_embedded_queue_worker=False,
    )
    with pytest.raises(RuntimeError, match="MAX_CONCURRENCY"):
        Settings(**base, ops_agent_max_concurrency=0).validate_for_startup()
    with pytest.raises(RuntimeError, match="DAILY_COST_LIMIT"):
        Settings(**base, ops_agent_daily_cost_limit_usd=0).validate_for_startup()
    with pytest.raises(RuntimeError, match="DATABASE_URL.*REDIS_URL"):
        Settings(**base, rapiin_database_url="postgresql://localhost/rapiin", rapiin_redis_url="").validate_for_startup()
    with pytest.raises(RuntimeError, match="PUBLIC_BASE_URL"):
        Settings(**base, ops_telegram_bot_token="secret", ops_telegram_chat_id="owner", ops_public_base_url="http://localhost").validate_for_startup()


def test_production_config_loads_secret_files(tmp_path):
    from rapiin.config import Settings
    secret = tmp_path / "server-secret"
    password = tmp_path / "supervisor-password"
    monitoring = tmp_path / "monitoring-token"
    ai_key = tmp_path / "ai-key"
    secret.write_text("s" * 40)
    password.write_text("StrongSupervisorPassword123")
    monitoring.write_text("m" * 40)
    ai_key.write_text("provider-key")
    settings = Settings(
        rapiin_env="production", rapiin_init_supervisor_email="ops@example.id",
        rapiin_allowed_origins="https://rapiin.example.id",
        rapiin_secret_key_file=str(secret), rapiin_init_supervisor_password_file=str(password),
            rapiin_monitoring_token_file=str(monitoring), ai_api_key_file=str(ai_key),
            rapiin_allow_public_registration=False,
            rapiin_embedded_queue_worker=False,
        )
    settings.validate_for_startup()
    assert settings.rapiin_secret_key == "s" * 40
    assert settings.ai_api_key == "provider-key"
