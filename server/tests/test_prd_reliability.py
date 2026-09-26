import json
import threading


def _device(client, email):
    body = client.post("/api/auth/register", json={
        "email": email, "name": email.split("@")[0], "password": "Password123!",
        "device_name": email, "os": "Test OS", "agent_version": "1.0",
    }).json()
    return body["user_id"], body["device"]["id"], body["device"]["device_key"]


def test_two_devices_claim_only_their_own_jobs(client):
    from rapiin.agent_jobs import enqueue_job
    from rapiin.database import db_session

    u1, d1, k1 = _device(client, "concurrent-1@example.com")
    u2, d2, k2 = _device(client, "concurrent-2@example.com")
    with db_session() as conn:
        j1 = enqueue_job(conn, task_id=None, device_id=d1, user_id=u1, kind="filesystem_scanner", payload={})
        j2 = enqueue_job(conn, task_id=None, device_id=d2, user_id=u2, kind="filesystem_scanner", payload={})

    results = {}
    def poll(name, device_id, key):
        results[name] = client.post("/api/agent/poll", json={"device_id": device_id, "device_key": key}).json()["job"]["id"]

    threads = [threading.Thread(target=poll, args=("a", d1, k1)), threading.Thread(target=poll, args=("b", d2, k2))]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert results == {"a": j1, "b": j2}


def test_same_user_can_keep_multiple_devices_online(client):
    body = client.post("/api/auth/register", json={
        "email": "multi@example.com", "name": "Multi", "password": "Password123!",
        "device_name": "Laptop", "os": "Test", "agent_version": "1.0",
    }).json()
    second = client.post(
        "/api/auth/register-device",
        json={"device_name": "Desktop", "os": "Test", "agent_version": "1.0"},
        headers={"Authorization": f"Bearer {body['token']}"},
    )
    assert second.status_code == 200
    from rapiin.database import db_session
    with db_session() as conn:
        rows = conn.execute("SELECT status FROM devices WHERE user_id = ?", (body["user_id"],)).fetchall()
    assert len(rows) == 2
    assert {row["status"] for row in rows} == {"ONLINE"}


def test_message_targets_explicit_owned_online_device(client, monkeypatch):
    body = client.post("/api/auth/register", json={
        "email": "routing@example.com", "name": "Routing", "password": "Password123!",
        "device_name": "Laptop", "os": "Test", "agent_version": "1.0",
    }).json()
    token = body["token"]
    second = client.post(
        "/api/auth/register-device",
        json={"device_name": "Desktop", "os": "Test", "agent_version": "1.0"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    monkeypatch.setattr("rapiin.worker.spawn_conversation_task", lambda **_kwargs: None)
    conversation = client.post(
        "/api/user/conversations", json={}, headers={"Authorization": f"Bearer {token}"}
    ).json()
    response = client.post(
        f"/api/user/conversations/{conversation['conversation_id']}/messages",
        json={"content": "scan folder", "device_id": second["device_id"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    from rapiin.database import db_session
    with db_session() as conn:
        task = conn.execute("SELECT device_id FROM tasks WHERE id = ?", (response.json()["task_id"],)).fetchone()
    assert task["device_id"] == second["device_id"]


def test_message_requires_selection_when_multiple_devices_are_online(client, monkeypatch):
    body = client.post("/api/auth/register", json={
        "email": "choose@example.com", "name": "Choose", "password": "Password123!",
        "device_name": "Laptop", "os": "Test", "agent_version": "1.0",
    }).json()
    token = body["token"]
    client.post(
        "/api/auth/register-device",
        json={"device_name": "Desktop", "os": "Test", "agent_version": "1.0"},
        headers={"Authorization": f"Bearer {token}"},
    )
    monkeypatch.setattr("rapiin.worker.spawn_conversation_task", lambda **_kwargs: None)
    conversation = client.post(
        "/api/user/conversations", json={}, headers={"Authorization": f"Bearer {token}"}
    ).json()
    response = client.post(
        f"/api/user/conversations/{conversation['conversation_id']}/messages",
        json={"content": "scan folder"}, headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 409
    assert "Pilih perangkat" in response.json()["detail"]


def test_message_rejects_unowned_or_offline_device(client, monkeypatch):
    owner = client.post("/api/auth/register", json={
        "email": "owner@example.com", "name": "Owner", "password": "Password123!",
        "device_name": "Owner laptop", "os": "Test", "agent_version": "1.0",
    }).json()
    other = client.post("/api/auth/register", json={
        "email": "other@example.com", "name": "Other", "password": "Password123!",
        "device_name": "Other laptop", "os": "Test", "agent_version": "1.0",
    }).json()
    monkeypatch.setattr("rapiin.worker.spawn_conversation_task", lambda **_kwargs: None)
    headers = {"Authorization": f"Bearer {owner['token']}"}
    conversation = client.post("/api/user/conversations", json={}, headers=headers).json()
    endpoint = f"/api/user/conversations/{conversation['conversation_id']}/messages"
    assert client.post(endpoint, json={"content": "x", "device_id": other["device"]["id"]}, headers=headers).status_code == 404
    from rapiin.database import db_session
    with db_session() as conn:
        conn.execute("UPDATE devices SET status = 'OFFLINE' WHERE id = ?", (owner["device"]["id"],))
    offline = client.post(endpoint, json={"content": "x", "device_id": owner["device"]["id"]}, headers=headers)
    assert offline.status_code == 409
    assert "offline" in offline.json()["detail"]


def test_expired_claim_is_requeued_and_claimed_again(client):
    from rapiin.agent_jobs import claim_next_job, enqueue_job
    from rapiin.database import db_session
    from rapiin.devices import _hash_device_key
    user_id, device_id, key = _device(client, "lease@example.com")
    with db_session() as conn:
        job_id = enqueue_job(conn, task_id=None, device_id=device_id, user_id=user_id, kind="filesystem_scanner", payload={})
        first = claim_next_job(conn, device_id=device_id, claimed_by_key_hash=_hash_device_key(key))
        assert first["id"] == job_id
        conn.execute("UPDATE agent_jobs SET lease_expires_at = '2000-01-01T00:00:00+00:00' WHERE id = ?", (job_id,))
        second = claim_next_job(conn, device_id=device_id, claimed_by_key_hash=_hash_device_key(key))
        assert second["id"] == job_id
        assert second["attempt_count"] == 2


def test_claimed_job_lease_can_be_renewed_by_owning_device(client):
    from rapiin.agent_jobs import claim_next_job, enqueue_job
    from rapiin.database import db_session
    from rapiin.devices import _hash_device_key
    user_id, device_id, key = _device(client, "renew@example.com")
    with db_session() as conn:
        job_id = enqueue_job(conn, task_id=None, device_id=device_id, user_id=user_id, kind="filesystem_scanner", payload={})
        claim_next_job(conn, device_id=device_id, claimed_by_key_hash=_hash_device_key(key))
        conn.execute("UPDATE agent_jobs SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (job_id,))
    response = client.post("/api/agent/lease/renew", json={"job_id": job_id, "device_id": device_id, "device_key": key})
    assert response.status_code == 200
    with db_session() as conn:
        lease = conn.execute("SELECT lease_expires_at FROM agent_jobs WHERE id=?", (job_id,)).fetchone()["lease_expires_at"]
    assert lease > "2000-01-01T00:00:00+00:00"


def test_task_progress_exposes_processed_and_total_counts(client):
    body = client.post("/api/auth/register", json={
        "email": "progress@example.com", "name": "Progress", "password": "Password123!",
        "device_name": "PC", "os": "Test", "agent_version": "1.0",
    }).json()
    token = body["token"]
    from rapiin.database import db_session
    from rapiin.tasks import create_task, update_task
    with db_session() as conn:
        task_id = create_task(conn, user_id=body["user_id"], device_id=body["device"]["id"], type="scan")
        update_task(conn, task_id, status="RUNNING", progress=78, processed_count=328, total_count=421)
    task = client.get(f"/api/user/tasks/{task_id}", headers={"Authorization": f"Bearer {token}"}).json()
    assert (task["progress"], task["processed_count"], task["total_count"]) == (78, 328, 421)


def test_terminal_task_sse_returns_authenticated_snapshot(client):
    body = client.post("/api/auth/register", json={
        "email": "stream@example.com", "name": "Stream", "password": "Password123!",
        "device_name": "PC", "os": "Test", "agent_version": "1.0",
    }).json()
    from rapiin.database import db_session
    from rapiin.tasks import create_task, update_task
    with db_session() as conn:
        task_id = create_task(conn, user_id=body["user_id"], device_id=None, type="chat")
        update_task(conn, task_id, status="COMPLETED", progress=100, processed_count=10, total_count=10)
    response = client.get(
        f"/api/user/tasks/{task_id}/events",
        headers={"Authorization": f"Bearer {body['token']}"},
    )
    assert response.status_code == 200
    assert '"type": "progress"' in response.text
    assert '"processed_count": 10' in response.text


def test_device_local_path_is_delegated_without_server_path_rewrite(monkeypatch):
    from rapiin.agent.core import HermesCore
    external_device_path = "/Users/employee/Downloads"
    core = HermesCore(object())
    monkeypatch.setattr(core, "_try_delegate_to_device", lambda *_args: {"status": "OK", "directory": external_device_path})
    result = core._execute_tool(
        conn=object(), user_id=1, task_id=1, device_id=1,
        name="folder_organizer", arguments={"path": external_device_path}, permissions=None,
    )
    assert result["directory"] == external_device_path


def test_ai_wait_does_not_hold_sqlite_write_lock(client):
    from rapiin.agent.core import HermesCore
    from rapiin.database import connect, db_session
    from rapiin.tasks import create_task, update_task

    body = client.post("/api/auth/register", json={
        "email": "lock-release@example.com", "name": "Lock", "password": "Password123!",
        "device_name": "PC", "os": "Test", "agent_version": "1.0",
    }).json()

    class Provider:
        def tools_schema(self): return []
        def chat_stream(self, _messages, tools=None, on_delta=None):
            other = connect()
            try:
                other.execute("PRAGMA busy_timeout=100")
                other.execute(
                    "INSERT INTO metric_events(name,value,timestamp) VALUES ('concurrent_write',1,'now')"
                )
                other.commit()
            finally:
                other.close()
            return {"message": {"role": "assistant", "content": "siap"}, "latency_ms": 1}

    with db_session() as conn:
        task_id = create_task(conn, user_id=body["user_id"], device_id=body["device"]["id"], type="chat")
        update_task(conn, task_id, status="RUNNING", started=True)
        result = HermesCore(Provider()).run_user_conversation(
            conn,
            user_id=body["user_id"],
            conversation_history=[{"role": "user", "content": "halo"}],
            task_id=task_id,
            device_id=body["device"]["id"],
            on_delta=lambda _text: None,
        )
    assert result["final_response"] == "siap"


def test_ai_provider_streams_text_and_rebuilds_tool_calls(monkeypatch):
    import json

    from rapiin.ai.provider import OpenAICompatibleProvider

    chunks = [
        {"choices": [{"delta": {"content": "Halo "}}]},
        {"choices": [{"delta": {"content": "dunia"}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "file_", "arguments": '{"pa'}}]}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"name": "search", "arguments": 'th":"x"}'}}]}}]},
    ]

    class FakeResponse:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def iter_lines(self):
            return iter(["data: " + json.dumps(item) for item in chunks] + ["data: [DONE]"])

    class FakeClient:
        def __init__(self, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def stream(self, *_args, **_kwargs): return FakeResponse()

    monkeypatch.setattr("rapiin.ai.provider.httpx.Client", FakeClient)
    deltas = []
    result = OpenAICompatibleProvider(base_url="http://provider", api_key="x").chat_stream([], on_delta=deltas.append)
    assert result["message"]["content"] == "Halo dunia"
    assert result["message"]["tool_calls"][0]["function"] == {"name": "file_search", "arguments": '{"path":"x"}'}
    assert deltas == ["Halo ", "dunia"]


def test_ai_provider_stream_retries_transient_status(monkeypatch):
    from rapiin.ai.provider import OpenAICompatibleProvider

    attempts = {"count": 0}

    class FakeResponse:
        def __init__(self, status_code): self.status_code = status_code
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self): return b"temporary"
        def iter_lines(self):
            return iter(['data: {"choices":[{"delta":{"content":"siap"}}]}', "data: [DONE]"])

    class FakeClient:
        def __init__(self, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def stream(self, *_args, **_kwargs):
            attempts["count"] += 1
            return FakeResponse(503 if attempts["count"] == 1 else 200)

    monkeypatch.setattr("rapiin.ai.provider.httpx.Client", FakeClient)
    monkeypatch.setattr("rapiin.ai.provider.time.sleep", lambda _seconds: None)
    result = OpenAICompatibleProvider(base_url="http://provider", api_key="x").chat_stream([])
    assert attempts["count"] == 2
    assert result["message"]["content"] == "siap"


def test_ai_provider_stream_accepts_non_stream_json_compatibility_response(monkeypatch):
    from rapiin.ai.provider import OpenAICompatibleProvider

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/json"}
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def json(self):
            return {"choices": [{"message": {"role": "assistant", "content": "siap"}}]}

    class FakeClient:
        def __init__(self, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def stream(self, *_args, **_kwargs): return FakeResponse()

    monkeypatch.setattr("rapiin.ai.provider.httpx.Client", FakeClient)
    deltas = []
    result = OpenAICompatibleProvider(base_url="http://provider", api_key="x").chat_stream([], on_delta=deltas.append)
    assert result["message"]["content"] == "siap"
    assert deltas == ["siap"]


def test_ai_provider_empty_stream_falls_back_to_non_stream(monkeypatch):
    from rapiin.ai.provider import OpenAICompatibleProvider

    class StreamResponse:
        status_code = 200
        headers = {"content-type": "text/event-stream"}
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def iter_lines(self): return iter(["data: [DONE]"])

    class JsonResponse:
        status_code = 200
        headers = {"content-type": "application/json"}
        def json(self):
            return {"choices": [{"message": {"role": "assistant", "content": "pulih"}}]}

    class FakeClient:
        def __init__(self, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def stream(self, *_args, **_kwargs): return StreamResponse()
        def post(self, *_args, **_kwargs): return JsonResponse()

    monkeypatch.setattr("rapiin.ai.provider.httpx.Client", FakeClient)
    deltas = []
    result = OpenAICompatibleProvider(base_url="http://provider", api_key="x").chat_stream([], on_delta=deltas.append)
    assert result["message"]["content"] == "pulih"
    assert deltas == ["pulih"]


def test_ai_provider_retries_invalid_success_payload(monkeypatch):
    from rapiin.ai.provider import OpenAICompatibleProvider

    attempts = {"count": 0}

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/json"}
        def json(self):
            attempts["count"] += 1
            if attempts["count"] == 1:
                return {"accepted": True}
            return {"choices": [{"message": {"role": "assistant", "content": "siap"}}]}

    class FakeClient:
        def __init__(self, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def post(self, *_args, **_kwargs): return FakeResponse()

    monkeypatch.setattr("rapiin.ai.provider.httpx.Client", FakeClient)
    monkeypatch.setattr("rapiin.ai.provider.time.sleep", lambda _seconds: None)
    result = OpenAICompatibleProvider(base_url="http://provider", api_key="x").chat([])
    assert result["message"]["content"] == "siap"
    assert attempts["count"] == 2


def test_ai_provider_retries_error_embedded_in_http_200_stream(monkeypatch):
    from rapiin.ai.provider import OpenAICompatibleProvider

    attempts = {"count": 0}

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/event-stream"}
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def iter_lines(self):
            attempts["count"] += 1
            if attempts["count"] == 1:
                return iter(['data: {"choices":[],"error":{"code":502}}', "data: [DONE]"])
            return iter(['data: {"choices":[{"delta":{"content":"siap"}}]}', "data: [DONE]"])

    class FakeClient:
        def __init__(self, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def stream(self, *_args, **_kwargs): return FakeResponse()

    monkeypatch.setattr("rapiin.ai.provider.httpx.Client", FakeClient)
    monkeypatch.setattr("rapiin.ai.provider.time.sleep", lambda _seconds: None)
    result = OpenAICompatibleProvider(base_url="http://provider", api_key="x").chat_stream([])
    assert result["message"]["content"] == "siap"
    assert attempts["count"] == 2


def test_recommendation_apply_uses_owned_task_snapshot(client):
    body = client.post("/api/auth/register", json={
        "email": "snapshot@example.com", "name": "Snapshot", "password": "Password123!",
        "device_name": "PC", "os": "Test", "agent_version": "1.0",
    }).json()
    token = body["token"]
    from rapiin.database import db_session
    from rapiin.tasks import create_task, update_task
    snapshot = {"tool_events": [{"tool": "folder_organizer", "status": "OK", "result": {
        "directory": "/device/Downloads", "recommendations": [{
            "id": "by-type", "kind": "create_folders_by_type", "apply": {
                "tool_name": "batch_executor", "tool_args": {"operation": "move", "moves": [
                    {"source": "/device/Downloads/a.pdf", "destination": "/device/Downloads/Dokumen",
                     "expected": {"path": "/device/Downloads/a.pdf", "size": 1, "mtime_ns": 1, "sha256": "abc"}}
                ]}
            }
        }]
    }}]}
    with db_session() as conn:
        task_id = create_task(conn, user_id=body["user_id"], device_id=body["device"]["id"], type="chat")
        update_task(conn, task_id, status="COMPLETED", result=snapshot, completed=True)
    response = client.post("/api/user/recommendations/apply", json={
        "source_task_id": task_id, "recommendation_id": "by-type",
        "recommendation": {"apply": {"tool_name": "file_delete", "tool_args": {"paths": ["/tampered"]}}},
    }, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    with db_session() as conn:
        approval = conn.execute("SELECT tool_name, tool_args FROM approvals WHERE id = ?", (response.json()["approval_id"],)).fetchone()
    assert approval["tool_name"] == "batch_executor"
    assert "/tampered" not in approval["tool_args"]


def test_recommendation_apply_accepts_device_agent_result_shape(client):
    body = client.post("/api/auth/register", json={
        "email": "device-snapshot@example.com", "name": "Device Snapshot", "password": "Password123!",
        "device_name": "PC", "os": "Test", "agent_version": "1.0",
    }).json()
    from rapiin.database import db_session
    from rapiin.tasks import create_task, update_task
    snapshot = {"tool_result": {
        "status": "OK", "directory": "/device/Downloads", "recommendations": [{
            "id": "by-year", "kind": "group_by_year", "apply": {
                "tool_name": "batch_executor", "tool_args": {"operation": "move", "moves": [{
                    "source": "/device/Downloads/laporan-2025.pdf",
                    "destination": "/device/Downloads/2025",
                    "expected": {"path": "/device/Downloads/laporan-2025.pdf", "size": 1,
                                 "mtime_ns": 1, "sha256": "abc"},
                }]},
            },
        }],
    }}
    with db_session() as conn:
        task_id = create_task(conn, user_id=body["user_id"], device_id=body["device"]["id"], type="chat")
        update_task(conn, task_id, status="COMPLETED", result=snapshot, completed=True)
    response = client.post("/api/user/recommendations/apply", json={
        "source_task_id": task_id, "recommendation_id": "by-year",
    }, headers={"Authorization": f"Bearer {body['token']}"})
    assert response.status_code == 200, response.text
    assert response.json()["tool"] == "batch_executor"


def test_expired_and_tampered_approval_snapshots_are_rejected(client):
    body = client.post("/api/auth/register", json={
        "email": "approval-snapshot@example.com", "name": "Approval", "password": "Password123!",
        "device_name": "PC", "os": "Test", "agent_version": "1.0",
    }).json()
    from rapiin.approval import create_approval, respond_approval
    from rapiin.database import db_session
    with db_session() as conn:
        expired = create_approval(conn, task_id=None, user_id=body["user_id"], requested_by="RAPIIN",
                                  kind="USER", action="delete", tool_name="file_delete", tool_args={"paths": ["a"]})
        conn.execute("UPDATE approvals SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (expired,))
        try:
            respond_approval(conn, expired, decision="APPROVED", decided_by_id=body["user_id"],
                             decided_by_name="Approval", decided_by_role="USER")
            assert False, "expired approval should fail"
        except ValueError as exc:
            assert "kedaluwarsa" in str(exc)
    with db_session() as conn:
        tampered = create_approval(conn, task_id=None, user_id=body["user_id"], requested_by="RAPIIN",
                                   kind="USER", action="delete", tool_name="file_delete", tool_args={"paths": ["a"]})
        conn.execute("UPDATE approvals SET tool_args=? WHERE id=?", (json.dumps({"paths": ["evil"]}), tampered))
        try:
            respond_approval(conn, tampered, decision="APPROVED", decided_by_id=body["user_id"],
                             decided_by_name="Approval", decided_by_role="USER")
            assert False, "tampered approval should fail"
        except ValueError as exc:
            assert "Snapshot approval berubah" in str(exc)


def test_device_wait_budget_supports_large_folder_scans():
    """A healthy leased agent may need over a minute for a large folder."""
    from rapiin.agent_jobs import LEASE_SECONDS, WAIT_BUDGET_SECONDS

    assert WAIT_BUDGET_SECONDS >= 120
    assert WAIT_BUDGET_SECONDS > LEASE_SECONDS
