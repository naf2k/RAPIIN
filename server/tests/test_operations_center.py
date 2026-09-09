"""Operations Center safety, deduplication, approvals, and RBAC."""
from .test_auth import _register_user


def _supervisor_headers(client):
    response = client.post("/api/auth/login", json={
        "email": "supervisor@beresin.example.com", "password": "Supervisor123!",
    })
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_ops_seeded_role_boundaries(client):
    response = client.get("/api/supervisor/ops/overview", headers=_supervisor_headers(client))
    assert response.status_code == 200
    agents = {item["role"]: item for item in response.json()["agents"]}
    assert set(agents) == {"LEAD", "SECURITY", "DIAGNOSTIC", "CODER"}
    import json
    assert json.loads(agents["LEAD"]["tool_policy"])["read_only"] is True
    coder = json.loads(agents["CODER"]["tool_policy"])
    assert coder["requires_fix_approval"] is True
    assert coder["isolated_worktree"] is True
    policies = client.get("/api/supervisor/ops/policies", headers=_supervisor_headers(client)).json()
    deploy = next(p for p in policies if p["key"] == "approvals.deployment")
    assert json.loads(deploy["value_json"])["separate_from_code_fix"] is True
    usage = client.get("/api/supervisor/ops/usage", headers=_supervisor_headers(client))
    assert usage.status_code == 200
    assert {row["role"] for row in usage.json()["agents"]} == {"LEAD", "SECURITY", "DIAGNOSTIC", "CODER"}
    assert usage.json()["daily_limit"] > 0


def test_audit_hash_chain_detects_tampering(client):
    from beresin.database import connect
    headers = _supervisor_headers(client)
    integrity = client.get("/api/supervisor/ops/audit/integrity", headers=headers)
    assert integrity.status_code == 200 and integrity.json()["valid"] is True
    conn = connect()
    row = conn.execute("SELECT id FROM audit_log ORDER BY id LIMIT 1").fetchone()
    conn.execute("UPDATE audit_log SET action='tampered' WHERE id=?", (row["id"],))
    conn.commit(); conn.close()
    broken = client.get("/api/supervisor/ops/audit/integrity", headers=headers).json()
    assert broken["valid"] is False
    assert broken["broken_at"] == row["id"]


def test_sanitized_audit_export_is_supervisor_only(client):
    assert client.get("/api/supervisor/ops/audit/export").status_code == 401
    exported = client.get("/api/supervisor/ops/audit/export?limit=10", headers=_supervisor_headers(client))
    assert exported.status_code == 200
    assert exported.json()["integrity"]["valid"] is True
    assert len(exported.json()["events"]) <= 10


def test_signal_deduplicates_and_timeline_is_auditable(client, monkeypatch):
    from beresin.config import settings
    monkeypatch.setattr(settings, "beresin_monitoring_token", "x" * 32)
    headers = {"Authorization": "Bearer " + "x" * 32}
    payload = {"source": "ci", "title": "Release tests failed", "severity": "HIGH", "summary": "2 tests failed", "resource": "main", "details": {"run": 42}}
    first = client.post("/api/internal/ops/signals", json=payload, headers=headers)
    second = client.post("/api/internal/ops/signals", json=payload, headers=headers)
    assert first.status_code == 200 and first.json()["created"] is True
    assert second.status_code == 200 and second.json()["created"] is False
    assert second.json()["occurrence_count"] == 2
    detail = client.get(f"/api/supervisor/ops/incidents/{first.json()['id']}", headers=_supervisor_headers(client)).json()
    assert [event["event_type"] for event in detail["events"]] == ["INCIDENT_OPENED", "SIGNAL_REPEATED"]


def test_code_and_deployment_use_separate_owner_approvals(client, monkeypatch):
    from beresin.config import settings
    monkeypatch.setattr(settings, "beresin_monitoring_token", "y" * 32)
    incident = client.post("/api/internal/ops/signals", headers={"Authorization": "Bearer " + "y" * 32}, json={"source": "security", "title": "Dependency vulnerability", "severity": "CRITICAL", "resource": "server"}).json()
    sup = _supervisor_headers(client)
    fix = client.post(f"/api/supervisor/ops/incidents/{incident['id']}/proposals", headers=sup, json={"action_type": "CODE_FIX", "title": "Patch dependency", "description": "Update affected package", "risk": "Regression"}).json()
    assert fix["approval_id"]
    approved = client.post(f"/api/supervisor/ops/approvals/{fix['approval_id']}/respond", headers=sup, json={"decision": "APPROVED", "note": "Proceed in worktree"})
    assert approved.status_code == 200
    assert client.get(f"/api/supervisor/ops/incidents/{incident['id']}", headers=sup).json()["status"] == "APPROVED_FOR_FIX"
    deploy = client.post(f"/api/supervisor/ops/incidents/{incident['id']}/proposals", headers=sup, json={"action_type": "DEPLOYMENT", "title": "Deploy verified patch", "description": "Roll out after checks", "risk": "Service restart"}).json()
    assert deploy["approval_id"] != fix["approval_id"]
    approvals = client.get("/api/supervisor/ops/approvals", headers=sup).json()
    assert {a["approval_type"] for a in approvals} == {"CODE_FIX", "DEPLOYMENT"}


def test_ops_approval_is_idempotent_expires_and_rejects_tampering(client, monkeypatch):
    from beresin.config import settings
    from beresin.database import connect
    monkeypatch.setattr(settings, "beresin_monitoring_token", "z" * 32)
    incident = client.post("/api/internal/ops/signals", headers={"Authorization": "Bearer " + "z" * 32}, json={"source": "ops", "title": "Guard approval", "severity": "HIGH"}).json()
    sup = _supervisor_headers(client)
    body = {"action_type": "CODE_FIX", "title": "Safe patch", "description": "Bounded", "risk": "Low", "idempotency_key": "incident-guard-001"}
    first = client.post(f"/api/supervisor/ops/incidents/{incident['id']}/proposals", headers=sup, json=body).json()
    second = client.post(f"/api/supervisor/ops/incidents/{incident['id']}/proposals", headers=sup, json=body).json()
    assert second == first
    conn = connect()
    conn.execute("UPDATE ops_action_proposals SET description='tampered' WHERE id=?", (first["proposal_id"],))
    conn.commit(); conn.close()
    rejected = client.post(f"/api/supervisor/ops/approvals/{first['approval_id']}/respond", headers=sup, json={"decision": "APPROVED", "note": "reviewed"})
    assert rejected.status_code == 409
    assert "berubah" in rejected.json()["detail"]


def test_pending_ops_approval_expires_automatically(client, monkeypatch):
    from beresin.config import settings
    from beresin.database import connect
    from beresin.ops_incidents import expire_pending_approvals
    monkeypatch.setattr(settings, "beresin_monitoring_token", "e" * 32)
    incident = client.post("/api/internal/ops/signals", headers={"Authorization": "Bearer " + "e" * 32}, json={"source": "ops", "title": "Expiry", "severity": "LOW"}).json()
    created = client.post(f"/api/supervisor/ops/incidents/{incident['id']}/proposals", headers=_supervisor_headers(client), json={"action_type": "CODE_FIX", "title": "Expiring", "description": "No action", "risk": "Low"}).json()
    conn = connect()
    conn.execute("UPDATE ops_approvals SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (created["approval_id"],))
    assert expire_pending_approvals(conn) == 1
    assert conn.execute("SELECT status FROM ops_approvals WHERE id=?", (created["approval_id"],)).fetchone()["status"] == "EXPIRED"
    assert conn.execute("SELECT status FROM ops_incidents WHERE id=?", (incident["id"],)).fetchone()["status"] == "INVESTIGATING"
    conn.close()


def test_nonurgent_incidents_are_grouped_into_one_daily_digest(client, monkeypatch):
    from beresin.database import connect
    from beresin.ops_incidents import ingest_signal, queue_daily_digest
    conn = connect()
    first = ingest_signal(conn, source="digest", title="Low one", severity="LOW")
    ingest_signal(conn, source="digest", title="Medium two", severity="MEDIUM")
    original = conn.execute("SELECT channel,delivery_status FROM ops_notifications WHERE incident_id=?", (first["id"],)).fetchone()
    assert dict(original) == {"channel": "IN_APP", "delivery_status": "SKIPPED"}
    digest_id = queue_daily_digest(conn)
    assert digest_id
    assert queue_daily_digest(conn) is None
    digest = conn.execute("SELECT channel,delivery_status,body FROM ops_notifications WHERE id=?", (digest_id,)).fetchone()
    assert digest["channel"] == "TELEGRAM" and digest["delivery_status"] == "PENDING"
    assert "Low one" in digest["body"] and "Medium two" in digest["body"]
    conn.close()


def test_emergency_pause_is_supervisor_only_and_blocks_agent_claims(client):
    reg = _register_user(client)
    user_token = reg.json()["token"]
    denied = client.post("/api/supervisor/ops/emergency-pause", headers={"Authorization": f"Bearer {user_token}"}, json={"enabled": True, "reason": "no"})
    assert denied.status_code == 403
    sup = _supervisor_headers(client)
    paused = client.post("/api/supervisor/ops/emergency-pause", headers=sup, json={"enabled": True, "reason": "Investigasi keamanan"})
    assert paused.status_code == 200 and paused.json()["enabled"] is True
    device = reg.json()["device"]
    poll = client.post("/api/agent/poll", json={"device_id": device["id"], "device_key": device["device_key"]})
    assert poll.status_code == 200
    assert poll.json()["operations_paused"] is True


def test_invalid_monitor_credential_is_rejected(client):
    response = client.post("/api/internal/ops/signals", headers={"Authorization": "Bearer wrong"}, json={"source": "ci", "title": "Failure", "severity": "HIGH"})
    assert response.status_code == 403


def test_audit_chain_detects_tampering_and_integrity_endpoint_is_supervisor_only(client):
    from beresin.audit import record_audit, verify_audit_chain
    from beresin.database import connect
    conn = connect()
    record_audit(conn, actor="system", actor_role="SYSTEM", action="first")
    second = record_audit(conn, actor="system", actor_role="SYSTEM", action="second")
    conn.commit()
    assert verify_audit_chain(conn)["valid"] is True
    conn.execute("UPDATE audit_log SET action='tampered' WHERE id=?", (second,))
    conn.commit()
    assert verify_audit_chain(conn) == {"valid": False, "count": 1, "broken_at": second}
    conn.close()
    assert client.get("/api/supervisor/ops/audit/integrity").status_code == 401


def test_recovered_device_signal_is_auto_resolved(client):
    from beresin.database import connect
    from beresin.ops_incidents import collect_runtime_signals, ingest_signal
    conn = connect()
    incident = ingest_signal(conn, source="device-monitor", title="Desktop agent offline", severity="HIGH", resource="devices")
    collect_runtime_signals(conn)
    row = conn.execute("SELECT status,resolved_at FROM ops_incidents WHERE id=?", (incident["id"],)).fetchone()
    assert row["status"] == "RESOLVED"
    assert row["resolved_at"]
    assert conn.execute("SELECT COUNT(*) n FROM ops_incident_events WHERE incident_id=? AND event_type='AUTO_RESOLVED'", (incident["id"],)).fetchone()["n"] == 1
    conn.close()


def test_prometheus_contains_operations_metrics(client, monkeypatch):
    from beresin.config import settings
    monkeypatch.setattr(settings, "beresin_monitoring_token", "m" * 32)
    response = client.get("/internal/metrics", headers={"Authorization": "Bearer " + "m" * 32})
    assert response.status_code == 200
    assert "beresin_ops_active_incidents" in response.text
    assert "beresin_ops_pending_approvals" in response.text
