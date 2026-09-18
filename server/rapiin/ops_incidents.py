"""Operations Center incident engine and immutable safety policies."""
from __future__ import annotations

import hashlib
import hmac
import json
import shutil
from datetime import datetime, timedelta, timezone

from .audit import record_audit
from .config import settings
from .database import utcnow_iso
from .ops_adapter import ROLE_TOOLS
from .ops_safety import content_hash, sanitize, sanitize_text

ACTIVE_STATUSES = (
    "OPEN", "INVESTIGATING", "AWAITING_APPROVAL", "APPROVED_FOR_FIX", "FIXING",
    "VERIFYING", "AWAITING_DEPLOY_APPROVAL", "DEPLOYING",
)
SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
# Mirrors the free-space threshold in ops/local_health_monitor.py.
DISK_ALERT_FREE_PERCENT = 10.0
ROLE_POLICIES = {
    "LEAD": {"read_only": True, "may_change_code": False, "may_deploy": False, "purpose": "triage_and_coordinate"},
    "SECURITY": {"read_only": True, "may_change_code": False, "may_deploy": False, "purpose": "security_review"},
    "DIAGNOSTIC": {"read_only": True, "may_change_code": False, "may_deploy": False, "purpose": "collect_evidence"},
    "CODER": {"read_only": False, "may_change_code": True, "may_deploy": False, "requires_fix_approval": True, "isolated_worktree": True, "purpose": "approved_code_fix"},
}


def seed_ops(conn) -> None:
    now = utcnow_iso()
    for role, policy in ROLE_POLICIES.items():
        conn.execute(
            """INSERT INTO ops_agents(name,role,state,model_policy,tool_policy,environment_scope,created_at,updated_at)
               VALUES(?,?,'IDLE','{}',?, ?,?,?) ON CONFLICT(role) DO UPDATE SET
               tool_policy=excluded.tool_policy, environment_scope=excluded.environment_scope, updated_at=excluded.updated_at""",
            (role.title(), role, json.dumps({**policy, "allowed_tools": sorted(ROLE_TOOLS[role])}), json.dumps({"workspace": "isolated_worktree" if role == "CODER" else "read_only"}), now, now),
        )
    defaults = {
        "operations.freeze": {"enabled": False, "reason": None},
        "approvals.code_fix": {"required": True, "approver_role": "SUPERVISOR"},
        "approvals.deployment": {"required": True, "approver_role": "SUPERVISOR", "separate_from_code_fix": True},
        "execution.coder": {"requires_fix_approval": True, "isolated_worktree": True, "direct_production_access": False},
    }
    for key, value in defaults.items():
        conn.execute(
            "INSERT INTO ops_policies(key,value_json,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO NOTHING",
            (key, json.dumps(value), now),
        )


def fingerprint(source: str, title: str, resource: str | None) -> str:
    raw = "|".join((source.strip().lower(), title.strip().lower(), (resource or "").strip().lower()))
    return hashlib.sha256(raw.encode()).hexdigest()


def _event(conn, incident_id: int, event_type: str, actor: str, actor_role: str | None, payload: dict | None = None) -> None:
    conn.execute(
        "INSERT INTO ops_incident_events(incident_id,event_type,actor,actor_role,payload_json,created_at) VALUES(?,?,?,?,?,?)",
        (incident_id, event_type, actor, actor_role, json.dumps(payload or {}, ensure_ascii=False), utcnow_iso()),
    )


def ingest_signal(conn, *, source: str, title: str, severity: str, summary: str = "", resource: str | None = None, details: dict | None = None) -> dict:
    seed_ops(conn)
    severity = severity.upper()
    if severity not in SEVERITIES:
        raise ValueError("Severity tidak valid.")
    title = sanitize_text(title, 200)
    summary = sanitize_text(summary, 4000)
    resource = sanitize_text(resource, 500) if resource else None
    details = sanitize(details or {})
    fp = fingerprint(source, title, resource)
    placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
    row = conn.execute(
        f"SELECT * FROM ops_incidents WHERE fingerprint=? AND status IN ({placeholders}) ORDER BY id DESC LIMIT 1",  # nosec B608 -- generated placeholders only
        (fp, *ACTIVE_STATUSES),
    ).fetchone()
    now = utcnow_iso()
    if row:
        incident_id = row["id"]
        # A repeated signal often carries a fresh measurement, so the stored
        # summary is refreshed instead of freezing on the first value seen.
        sets = ["occurrence_count=occurrence_count+1", "last_seen_at=?", "updated_at=?", "severity=?"]
        values: list = [now, now, severity]
        if summary and summary != (row["summary"] or ""):
            sets.insert(0, "summary=?")
            values.insert(0, summary)
        values.append(incident_id)
        conn.execute(f"UPDATE ops_incidents SET {', '.join(sets)} WHERE id=?", values)  # nosec B608 -- fragments are fixed constants
        _event(conn, incident_id, "SIGNAL_REPEATED", "system", "SYSTEM", {"evidence_hash": content_hash(details)})
        created = False
    else:
        cur = conn.execute(
            """INSERT INTO ops_incidents(fingerprint,title,severity,status,summary,source,affected_resource,first_seen_at,last_seen_at,created_at,updated_at)
               VALUES(?,?,?,'OPEN',?,?,?,?,?,?,?)""",
            (fp, title.strip(), severity, summary, source.strip(), resource, now, now, now, now),
        )
        incident_id = cur.lastrowid
        conn.execute(
            "INSERT INTO ops_evidence(incident_id,kind,source,content_json,content_hash,created_at) VALUES(?,?,?,?,?,?)",
            (incident_id, "SIGNAL", source.strip(), json.dumps(details, ensure_ascii=False), content_hash(details), now),
        )
        _event(conn, incident_id, "INCIDENT_OPENED", "system", "SYSTEM", {"evidence_hash": content_hash(details)})
        conn.execute(
            "INSERT INTO ops_notifications(incident_id,channel,title,body,severity,delivery_status,created_at) VALUES(?,?,?,?,?,?,?)",
            (incident_id, "TELEGRAM" if severity in {"HIGH", "CRITICAL"} else "IN_APP",
             f"Insiden {severity}: {title.strip()}", summary, severity,
             "PENDING" if severity in {"HIGH", "CRITICAL"} else "SKIPPED", now),
        )
        created = True
    record_audit(conn, actor="system", actor_role="SYSTEM", action="ops_signal_ingested", resource=f"ops-incident:{incident_id}")
    return {**get_incident(conn, incident_id), "created": created}


def list_incidents(conn, status: str | None = None, severity: str | None = None, limit: int = 100) -> list[dict]:
    where, args = [], []
    if status:
        where.append("status=?"); args.append(status.upper())
    if severity:
        where.append("severity=?"); args.append(severity.upper())
    sql = "SELECT * FROM ops_incidents" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 ELSE 4 END, last_seen_at DESC LIMIT ?"  # nosec B608 -- clauses are fixed constants
    return [dict(r) for r in conn.execute(sql, (*args, min(max(limit, 1), 500))).fetchall()]


def get_incident(conn, incident_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM ops_incidents WHERE id=?", (incident_id,)).fetchone()
    if not row:
        return None
    result = dict(row)
    result["events"] = [{**dict(e), "payload": json.loads(e["payload_json"])} for e in conn.execute("SELECT * FROM ops_incident_events WHERE incident_id=? ORDER BY id", (incident_id,)).fetchall()]
    result["proposals"] = [dict(r) for r in conn.execute("SELECT * FROM ops_action_proposals WHERE incident_id=? ORDER BY id DESC", (incident_id,)).fetchall()]
    result["approvals"] = [dict(r) for r in conn.execute("SELECT * FROM ops_approvals WHERE incident_id=? ORDER BY id DESC", (incident_id,)).fetchall()]
    result["assignments"] = [dict(r) for r in conn.execute("SELECT a.*,g.role,g.name agent_name FROM ops_agent_assignments a JOIN ops_agents g ON g.id=a.agent_id WHERE a.incident_id=? ORDER BY a.id", (incident_id,)).fetchall()]
    result["agent_messages"] = [dict(r) for r in conn.execute("SELECT m.*,g.role sender_role FROM ops_agent_messages m LEFT JOIN ops_agents g ON g.id=m.sender_agent_id WHERE m.incident_id=? ORDER BY m.id", (incident_id,)).fetchall()]
    changes = [dict(r) for r in conn.execute("SELECT * FROM ops_code_changes WHERE incident_id=? ORDER BY id DESC", (incident_id,)).fetchall()]
    for change in changes:
        change["checks"] = [dict(r) for r in conn.execute("SELECT * FROM ops_check_runs WHERE code_change_id=? ORDER BY id", (change["id"],)).fetchall()]
    result["code_changes"] = changes
    result["deployments"] = [dict(r) for r in conn.execute("SELECT * FROM ops_deployments WHERE incident_id=? ORDER BY id DESC", (incident_id,)).fetchall()]
    return result


def _approval_snapshot(incident_id: int, proposal_id: int, action_type: str, title: str, description: str, risk: str) -> str:
    return hashlib.sha256(json.dumps({
        "incident_id": incident_id, "proposal_id": proposal_id,
        "action_type": action_type, "title": title, "description": description,
        "risk": risk,
    }, sort_keys=True).encode()).hexdigest()


def create_proposal(conn, incident_id: int, *, action_type: str, title: str, description: str, risk: str, actor: dict, idempotency_key: str | None = None) -> dict:
    if not get_incident(conn, incident_id):
        raise LookupError("Insiden tidak ditemukan.")
    action_type = action_type.upper()
    if action_type not in {"INVESTIGATION", "CODE_FIX", "DEPLOYMENT"}:
        raise ValueError("Jenis proposal tidak valid.")
    now = utcnow_iso()
    if idempotency_key:
        existing = conn.execute(
            "SELECT proposal_id,id FROM ops_approvals WHERE idempotency_key=?",
            (idempotency_key,),
        ).fetchone()
        if existing:
            return {"proposal_id": existing["proposal_id"], "approval_id": existing["id"]}
    cur = conn.execute(
        "INSERT INTO ops_action_proposals(incident_id,action_type,title,description,risk,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
        (incident_id, action_type, title, description, risk, now, now),
    )
    approval_id = None
    if action_type in {"CODE_FIX", "DEPLOYMENT"}:
        approval_type = action_type
        snapshot_hash = _approval_snapshot(incident_id, cur.lastrowid, action_type, title, description, risk)
        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=15 if action_type == "DEPLOYMENT" else 30)).isoformat()
        approval_id = conn.execute(
            "INSERT INTO ops_approvals(incident_id,proposal_id,approval_type,snapshot_hash,idempotency_key,requested_at,expires_at) VALUES(?,?,?,?,?,?,?)",
            (incident_id, cur.lastrowid, approval_type, snapshot_hash, idempotency_key, now, expires_at),
        ).lastrowid
        conn.execute("UPDATE ops_incidents SET status=?,updated_at=? WHERE id=?", ("AWAITING_APPROVAL" if action_type == "CODE_FIX" else "AWAITING_DEPLOY_APPROVAL", now, incident_id))
    _event(conn, incident_id, "PROPOSAL_CREATED", actor["name"], actor["role"], {"proposal_id": cur.lastrowid, "approval_id": approval_id, "action_type": action_type})
    record_audit(conn, actor=actor["name"], actor_role=actor["role"], user_id=actor["id"], action="ops_proposal_created", resource=f"ops-incident:{incident_id}")
    return {"proposal_id": cur.lastrowid, "approval_id": approval_id}


def respond_approval(conn, approval_id: int, *, decision: str, note: str, actor: dict) -> dict:
    decision = decision.upper()
    if decision not in {"APPROVED", "REJECTED"}:
        raise ValueError("Keputusan harus APPROVED atau REJECTED.")
    row = conn.execute("SELECT * FROM ops_approvals WHERE id=?", (approval_id,)).fetchone()
    if not row:
        raise LookupError("Approval tidak ditemukan.")
    if row["status"] != "PENDING":
        raise ValueError("Approval sudah diputuskan.")
    now = utcnow_iso()
    if row["expires_at"] and row["expires_at"] <= now:
        conn.execute("UPDATE ops_approvals SET status='EXPIRED',decided_at=? WHERE id=?", (now, approval_id))
        raise ValueError("Approval sudah kedaluwarsa.")
    proposal = conn.execute("SELECT * FROM ops_action_proposals WHERE id=?", (row["proposal_id"],)).fetchone()
    expected_hash = _approval_snapshot(row["incident_id"], proposal["id"], proposal["action_type"], proposal["title"], proposal["description"], proposal["risk"] or "")
    if not hmac.compare_digest(row["snapshot_hash"] or "", expected_hash):
        raise ValueError("Isi proposal berubah setelah approval dibuat.")
    conn.execute("UPDATE ops_approvals SET status=?,decided_at=?,decided_by=?,decision_note=? WHERE id=?", (decision, now, actor["id"], note, approval_id))
    conn.execute("UPDATE ops_action_proposals SET status=?,updated_at=? WHERE id=?", (decision, now, row["proposal_id"]))
    if decision == "REJECTED":
        new_status = "REJECTED"
    elif row["approval_type"] == "CODE_FIX":
        new_status = "APPROVED_FOR_FIX"
    else:
        new_status = "DEPLOYING"
    conn.execute("UPDATE ops_incidents SET status=?,updated_at=? WHERE id=?", (new_status, now, row["incident_id"]))
    _event(conn, row["incident_id"], f"{row['approval_type']}_{decision}", actor["name"], actor["role"], {"approval_id": approval_id, "note": note})
    record_audit(conn, actor=actor["name"], actor_role=actor["role"], user_id=actor["id"], action="ops_approval_decided", resource=f"ops-approval:{approval_id}", result=decision)
    return dict(conn.execute("SELECT * FROM ops_approvals WHERE id=?", (approval_id,)).fetchone())


def expire_pending_approvals(conn) -> int:
    now = utcnow_iso()
    rows = conn.execute(
        "SELECT id,incident_id,proposal_id,approval_type FROM ops_approvals WHERE status='PENDING' AND expires_at IS NOT NULL AND expires_at <= ?",
        (now,),
    ).fetchall()
    for row in rows:
        conn.execute("UPDATE ops_approvals SET status='EXPIRED',decided_at=? WHERE id=?", (now, row["id"]))
        conn.execute("UPDATE ops_action_proposals SET status='CANCELLED',updated_at=? WHERE id=? AND status='PENDING'", (now, row["proposal_id"]))
        conn.execute("UPDATE ops_incidents SET status='INVESTIGATING',updated_at=? WHERE id=? AND status IN ('AWAITING_APPROVAL','AWAITING_DEPLOY_APPROVAL')", (now, row["incident_id"]))
        _event(conn, row["incident_id"], f"{row['approval_type']}_EXPIRED", "system", "SYSTEM", {"approval_id": row["id"]})
        record_audit(conn, actor="system", actor_role="SYSTEM", action="ops_approval_expired", resource=f"ops-approval:{row['id']}", result="EXPIRED")
    return len(rows)


def queue_daily_digest(conn) -> int | None:
    """Queue at most one remote digest per UTC day for non-urgent incidents."""
    today = datetime.now(timezone.utc).date().isoformat()
    key = "notifications.last_digest"
    row = conn.execute("SELECT value_json FROM ops_policies WHERE key=?", (key,)).fetchone()
    if row and json.loads(row["value_json"]).get("date") == today:
        return None
    incidents = conn.execute(
        "SELECT id,title,severity FROM ops_incidents WHERE severity IN ('LOW','MEDIUM') AND status NOT IN ('RESOLVED','REJECTED') ORDER BY severity,id"
    ).fetchall()
    if not incidents:
        return None
    now = utcnow_iso()
    summary = "; ".join(f"#{item['id']} {item['severity']} {item['title']}" for item in incidents[:10])
    notification_id = conn.execute(
        "INSERT INTO ops_notifications(channel,title,body,severity,delivery_status,created_at) VALUES('TELEGRAM','RAPIIN daily operations digest',?,'MEDIUM','PENDING',?)",
        (summary[:2000], now),
    ).lastrowid
    conn.execute(
        "INSERT INTO ops_policies(key,value_json,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",
        (key, json.dumps({"date": today, "notification_id": notification_id}), now),
    )
    return notification_id


def set_incident_status(conn, incident_id: int, status: str, actor: dict, note: str = "") -> dict:
    allowed = {"INVESTIGATING", "VERIFYING", "RESOLVED", "OPEN"}
    status = status.upper()
    if status not in allowed:
        raise ValueError("Transisi status manual tidak diizinkan.")
    if not get_incident(conn, incident_id):
        raise LookupError("Insiden tidak ditemukan.")
    now = utcnow_iso()
    conn.execute("UPDATE ops_incidents SET status=?,updated_at=?,resolved_at=? WHERE id=?", (status, now, now if status == "RESOLVED" else None, incident_id))
    _event(conn, incident_id, f"STATUS_{status}", actor["name"], actor["role"], {"note": note})
    record_audit(conn, actor=actor["name"], actor_role=actor["role"], user_id=actor["id"], action="ops_incident_status_changed", resource=f"ops-incident:{incident_id}")
    return get_incident(conn, incident_id)


def set_freeze(conn, enabled: bool, reason: str, actor: dict) -> dict:
    now = utcnow_iso()
    value = {"enabled": bool(enabled), "reason": reason.strip() or None, "changed_at": now}
    conn.execute("INSERT INTO ops_policies(key,value_json,updated_by,updated_at) VALUES('operations.freeze',?,?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_by=excluded.updated_by,updated_at=excluded.updated_at", (json.dumps(value), actor["id"], now))
    _event_for_all = conn.execute(f"SELECT id FROM ops_incidents WHERE status IN ({','.join('?' for _ in ACTIVE_STATUSES)})", ACTIVE_STATUSES).fetchall()  # nosec B608 -- generated placeholders only
    for row in _event_for_all:
        _event(conn, row["id"], "EMERGENCY_PAUSE_CHANGED", actor["name"], actor["role"], value)
    record_audit(conn, actor=actor["name"], actor_role=actor["role"], user_id=actor["id"], action="ops_emergency_pause_enabled" if enabled else "ops_emergency_pause_disabled", resource="ops-policy:operations.freeze")
    return value


def operations_frozen(conn) -> bool:
    row = conn.execute("SELECT value_json FROM ops_policies WHERE key='operations.freeze'").fetchone()
    if not row:
        return False
    try:
        return bool(json.loads(row["value_json"]).get("enabled"))
    except (TypeError, json.JSONDecodeError):
        return True  # fail closed when a safety policy is unreadable


def overview(conn) -> dict:
    seed_ops(conn)
    active = list_incidents(conn, limit=100)
    active = [i for i in active if i["status"] in ACTIVE_STATUSES]
    freeze = json.loads(conn.execute("SELECT value_json FROM ops_policies WHERE key='operations.freeze'").fetchone()["value_json"])
    counts = {s: sum(i["severity"] == s for i in active) for s in ("CRITICAL", "HIGH", "MEDIUM", "LOW")}
    approvals = conn.execute("SELECT COUNT(*) n FROM ops_approvals WHERE status='PENDING'").fetchone()["n"]
    agents = [dict(r) for r in conn.execute("SELECT * FROM ops_agents ORDER BY id").fetchall()]
    return {"status": "PAUSED" if freeze.get("enabled") else ("CRITICAL" if counts["CRITICAL"] else "DEGRADED" if active else "HEALTHY"), "freeze": freeze, "active_incidents": len(active), "severity_counts": counts, "pending_approvals": approvals, "agents": agents}


def collect_runtime_signals(conn) -> list[dict]:
    """Turn deterministic local runtime checks into deduplicated incidents."""
    created = []
    stale = conn.execute("SELECT COUNT(*) n FROM devices WHERE status='OFFLINE'").fetchone()["n"]
    if stale:
        created.append(ingest_signal(conn, source="device-monitor", title="Desktop agent offline", severity="HIGH", summary=f"{stale} perangkat offline.", resource="devices"))
    else:
        auto_resolve(conn, source="device-monitor", resource="devices", note="Semua desktop agent kembali online.")
    day_ago = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    fifteen_minutes_ago = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    failed = conn.execute("SELECT COUNT(*) n FROM tasks WHERE status='FAILED' AND created_at >= ?", (day_ago,)).fetchone()["n"]
    if failed:
        created.append(ingest_signal(conn, source="task-monitor", title="Task execution failed", severity="HIGH", summary=f"{failed} task gagal dalam 24 jam.", resource="tasks"))
    else:
        auto_resolve(conn, source="task-monitor", resource="tasks", note="Tidak ada task gagal dalam jendela 24 jam.")
    stuck = conn.execute("SELECT COUNT(*) n FROM agent_jobs WHERE status IN ('PENDING','CLAIMED') AND created_at < ?", (fifteen_minutes_ago,)).fetchone()["n"]
    if stuck:
        created.append(ingest_signal(conn, source="queue-monitor", title="Agent queue stuck", severity="CRITICAL", summary=f"{stuck} job melewati 15 menit.", resource="agent_jobs"))
    else:
        auto_resolve(conn, source="queue-monitor", resource="agent_jobs", note="Antrean kembali mengalir normal.")
    if settings.rapiin_redis_url:
        heartbeat = conn.execute("SELECT updated_at FROM ops_policies WHERE key='worker.conversation.heartbeat'").fetchone()
        worker_stale = not heartbeat or (datetime.now(timezone.utc) - datetime.fromisoformat(heartbeat["updated_at"])).total_seconds() > 30
        if worker_stale:
            created.append(ingest_signal(conn, source="operations-meta-monitor", title="Conversation worker heartbeat stale", severity="CRITICAL", summary="Redis worker tidak mengirim heartbeat dalam 30 detik.", resource="queue-worker"))
        else:
            auto_resolve(conn, source="operations-meta-monitor", resource="queue-worker", note="Redis worker heartbeat kembali normal.")
            auto_resolve(conn, source="local-health-monitor", resource="operations-runtime", note="Operations runtime dan queue worker kembali sehat.")
    # The laptop monitor reports disk pressure. A healthy disk simply stops
    # producing signals, so the incident is cleared here explicitly; otherwise
    # it would stay open forever with a frozen measurement.
    try:
        usage = shutil.disk_usage(settings.data_dir)
        free_percent = round((usage.free / usage.total) * 100, 1)
    except OSError:
        free_percent = None
    if free_percent is not None and free_percent >= DISK_ALERT_FREE_PERCENT:
        auto_resolve(
            conn,
            source="local-health-monitor",
            title="Disk space critically low",
            note=f"Ruang disk kembali normal ({free_percent}% tersisa).",
        )
    auto_resolve(conn, source="local-health-monitor", title="Server recovered after readiness failure", note="Recovery berhasil diverifikasi oleh readiness monitor.")
    return created


def auto_resolve(conn, *, source: str, resource: str | None = None, title: str | None = None, note: str) -> int:
    where = ["source=?", f"status IN ({','.join('?' for _ in ACTIVE_STATUSES)})"]
    args: list = [source, *ACTIVE_STATUSES]
    if resource is not None:
        where.append("affected_resource=?"); args.append(resource)
    if title is not None:
        where.append("title=?"); args.append(title)
    rows = conn.execute("SELECT id FROM ops_incidents WHERE " + " AND ".join(where), args).fetchall()  # nosec B608 -- clauses are fixed constants
    now = utcnow_iso()
    for row in rows:
        conn.execute("UPDATE ops_incidents SET status='RESOLVED',resolved_at=?,updated_at=? WHERE id=?", (now, now, row["id"]))
        _event(conn, row["id"], "AUTO_RESOLVED", "system", "SYSTEM", {"note": note})
        record_audit(conn, actor="system", actor_role="SYSTEM", action="ops_incident_auto_resolved", resource=f"ops-incident:{row['id']}")
    return len(rows)
