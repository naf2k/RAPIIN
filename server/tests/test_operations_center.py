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
