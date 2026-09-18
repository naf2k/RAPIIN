"""Bounded retention and reminder maintenance for Operations Center."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from .audit import record_audit
from .config import settings
from .database import utcnow_iso
from .ops_incidents import _event


def queue_approval_reminders(conn) -> int:
    """Create one reminder when a pending approval enters its last half-life."""
    now = datetime.now(timezone.utc)
    rows = conn.execute("SELECT * FROM ops_approvals WHERE status='PENDING' AND expires_at IS NOT NULL").fetchall()
    queued = 0
    for row in rows:
        requested = datetime.fromisoformat(row["requested_at"])
        expires = datetime.fromisoformat(row["expires_at"])
        if not (requested + (expires - requested) / 2 <= now < expires):
            continue
        exists = conn.execute("SELECT 1 FROM ops_incident_events WHERE incident_id=? AND event_type='APPROVAL_REMINDER' AND payload_json LIKE ?", (row["incident_id"], f'%"approval_id": {row["id"]}%')).fetchone()
        if exists:
            continue
        timestamp = utcnow_iso()
        conn.execute(
            "INSERT INTO ops_notifications(incident_id,channel,title,body,severity,delivery_status,created_at) VALUES(?,'TELEGRAM',?,?,'HIGH','PENDING',?)",
            (row["incident_id"], f"Approval {row['approval_type']} hampir kedaluwarsa", f"Review approval #{row['id']} di Operations Center.", timestamp),
        )
        _event(conn, row["incident_id"], "APPROVAL_REMINDER", "system", "SYSTEM", {"approval_id": row["id"]})
        queued += 1
    return queued


def apply_ops_retention(conn, days: int | None = None) -> dict:
    """Minimize old payloads while retaining hashes, metadata and audit timeline."""
    days = days or settings.ops_retention_days
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(days, 30))).isoformat()
    incidents = conn.execute("SELECT id FROM ops_incidents WHERE status IN ('RESOLVED','REJECTED') AND updated_at < ?", (cutoff,)).fetchall()
    minimized_messages = minimized_evidence = 0
    for incident in incidents:
        for row in conn.execute("SELECT id,content FROM ops_agent_messages WHERE incident_id=? AND content NOT LIKE '%retention_expired%'", (incident["id"],)).fetchall():
            digest = hashlib.sha256(row["content"].encode()).hexdigest()
            conn.execute("UPDATE ops_agent_messages SET content=? WHERE id=?", (json.dumps({"retention_expired": True, "content_hash": digest}), row["id"]))
            minimized_messages += 1
        for row in conn.execute("SELECT id FROM ops_evidence WHERE incident_id=? AND content_json != '{}'", (incident["id"],)).fetchall():
            conn.execute("UPDATE ops_evidence SET content_json='{}' WHERE id=?", (row["id"],))
            minimized_evidence += 1
    if minimized_messages or minimized_evidence:
        record_audit(conn, actor="system", actor_role="SYSTEM", action="ops_retention_applied", resource="ops-payloads", result=f"messages={minimized_messages},evidence={minimized_evidence}")
    return {"incidents": len(incidents), "messages": minimized_messages, "evidence": minimized_evidence}
