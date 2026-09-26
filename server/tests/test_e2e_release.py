"""Release-path E2E: local recommendation -> approval -> agent execution."""
from __future__ import annotations

import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[2] / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from rapiin_agent import config as agent_config  # noqa: E402
from rapiin_agent.local_tools import run_tool  # noqa: E402


def test_recommend_review_approve_execute_verify_end_to_end(client, tmp_path, monkeypatch):
    registration = client.post("/api/auth/register", json={
        "email": "release-e2e@example.com", "name": "Release E2E", "password": "Password123!",
        "device_name": "Release Device", "os": "Test OS", "agent_version": "1.0.0",
    }).json()
    token = registration["token"]
    workspace = tmp_path / "Downloads"
    workspace.mkdir()
    for index in range(5):
        (workspace / f"laporan-{index}.pdf").write_bytes(f"PDF-{index}".encode())
    monkeypatch.setattr(agent_config, "workspace_root", lambda: workspace)
    monkeypatch.setattr(agent_config, "allowed_roots", lambda: [workspace])

    paired = client.post("/api/auth/register-device", json={
        "device_name": "Release Device", "os": "Test OS", "agent_version": "1.0.0",
        "capabilities": ["folder_organizer", "batch_executor"], "workspace_root": str(workspace),
    }, headers={"Authorization": f"Bearer {token}"}).json()
    organizer_result = run_tool("folder_organizer", {"path": str(workspace)})
    assert organizer_result["status"] == "OK"
    recommendation = next(item for item in organizer_result["recommendations"] if item["id"] == "by-type")

    from rapiin.database import db_session
    from rapiin.tasks import create_task, update_task
    with db_session() as conn:
        source_task_id = create_task(conn, user_id=registration["user_id"], device_id=paired["device_id"], type="chat")
        update_task(conn, source_task_id, status="COMPLETED", completed=True, result={
            "tool_events": [{"tool": "folder_organizer", "status": "OK", "result": organizer_result}]
        })

    apply_response = client.post("/api/user/recommendations/apply", json={
        "source_task_id": source_task_id, "recommendation_id": recommendation["id"],
    }, headers={"Authorization": f"Bearer {token}"})
    assert apply_response.status_code == 200, apply_response.text
    approval_id = apply_response.json()["approval_id"]
    task_id = apply_response.json()["task_id"]
    approved = client.post(f"/api/user/approvals/{approval_id}/respond", json={"decision": "APPROVED"},
                           headers={"Authorization": f"Bearer {token}"})
    assert approved.status_code == 200

    poll = client.post("/api/agent/poll", json={"device_id": paired["device_id"], "device_key": paired["device_key"]}).json()
    assert poll["job"]["task_id"] == task_id
    arguments = poll["job"]["payload"]["arguments"]
    execution = run_tool(poll["job"]["kind"], arguments)
    assert execution["status"] == "OK"
    reported = client.post("/api/agent/result", json={
        "job_id": poll["job"]["id"], "device_id": paired["device_id"], "device_key": paired["device_key"],
        "status": "SUCCEEDED", "result": {"tool_result": execution},
    })
    assert reported.status_code == 200

    task = client.get(f"/api/user/tasks/{task_id}", headers={"Authorization": f"Bearer {token}"}).json()
    assert task["status"] == "COMPLETED"
    assert task["verified_count"] if "verified_count" in task else task["processed_count"] == 5
    assert not list(workspace.glob("*.pdf"))
    assert len(list((workspace / "Dokumen").glob("*.pdf"))) == 5
    with db_session() as conn:
        actions = {row["action"] for row in conn.execute("SELECT action FROM audit_log WHERE task_id=?", (task_id,)).fetchall()}
    assert {"approval_requested", "approval_approved", "agent_job_succeeded"} <= actions
