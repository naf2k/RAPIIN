import json

from rapiin.database import connect, utcnow_iso
from rapiin.ops_incidents import create_proposal, ingest_signal, seed_ops
from rapiin.ops_maintenance import apply_ops_retention, queue_approval_reminders
from rapiin.ops_runtime import provider_circuit_open


def _actor(conn):
    return dict(conn.execute("SELECT * FROM users WHERE role='SUPERVISOR' LIMIT 1").fetchone())


def test_approval_reminder_is_idempotent():
    conn = connect(); seed_ops(conn)
    incident = ingest_signal(conn, source="maintenance", title="Reminder", severity="HIGH")
    proposal = create_proposal(conn, incident["id"], action_type="CODE_FIX", title="Patch", description="Bounded", risk="Low", actor=_actor(conn))
    conn.execute("UPDATE ops_approvals SET requested_at='2000-01-01T00:00:00+00:00',expires_at='2999-01-01T00:00:00+00:00' WHERE id=?", (proposal["approval_id"],))
    # Force midpoint to have passed while expiry remains in the future.
    conn.execute("UPDATE ops_approvals SET requested_at='2020-01-01T00:00:00+00:00',expires_at='2030-01-01T00:00:00+00:00' WHERE id=?", (proposal["approval_id"],))
    assert queue_approval_reminders(conn) == 1
    assert queue_approval_reminders(conn) == 0
    conn.close()


def test_retention_minimizes_payload_but_keeps_hash():
    conn = connect(); seed_ops(conn)
    incident = ingest_signal(conn, source="maintenance", title="Old", severity="LOW", details={"private": "payload"})
    lead = conn.execute("SELECT id FROM ops_agents WHERE role='LEAD'").fetchone()
    conn.execute("INSERT INTO ops_agent_messages(incident_id,sender_agent_id,message_type,content,created_at) VALUES(?,?,'REPORT',?,?)", (incident["id"], lead["id"], json.dumps({"summary": "old content"}), utcnow_iso()))
    conn.execute("UPDATE ops_incidents SET status='RESOLVED',updated_at='2000-01-01T00:00:00+00:00' WHERE id=?", (incident["id"],))
    result = apply_ops_retention(conn, days=30)
    assert result["messages"] == 1 and result["evidence"] == 1
    message = json.loads(conn.execute("SELECT content FROM ops_agent_messages WHERE incident_id=?", (incident["id"],)).fetchone()["content"])
    assert message["retention_expired"] is True and len(message["content_hash"]) == 64
    evidence = conn.execute("SELECT content_json,content_hash FROM ops_evidence WHERE incident_id=?", (incident["id"],)).fetchone()
    assert evidence["content_json"] == "{}" and len(evidence["content_hash"]) == 64
    conn.close()


def test_provider_circuit_breaker_opens_after_bounded_failures(monkeypatch):
    from rapiin.config import settings
    conn = connect(); seed_ops(conn)
    agent = conn.execute("SELECT id FROM ops_agents WHERE role='LEAD'").fetchone()
    monkeypatch.setattr(settings, "ops_agent_failure_threshold", 2)
    for _ in range(2):
        conn.execute("INSERT INTO ops_agent_usage(agent_id,duration_ms,status,created_at) VALUES(?,0,'FAILED',?)", (agent["id"], utcnow_iso()))
    assert provider_circuit_open(conn) is True
    conn.close()
