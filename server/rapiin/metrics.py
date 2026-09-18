"""Observability metrics (PRD section 30).

Computed on demand from the audit log + tasks table. Supervisor sees an
aggregated, human-readable version.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from .database import utcnow_iso


def _parse_ts(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def compute_metrics(conn) -> dict:
    """Aggregate metrics over the last 24h (plus lifetime counters)."""
    now = datetime.now(timezone.utc)
    day_ago = (now - timedelta(hours=24)).isoformat()

    total_tasks = conn.execute("SELECT COUNT(*) AS n FROM tasks").fetchone()["n"]
    day_tasks = conn.execute("SELECT COUNT(*) AS n FROM tasks WHERE created_at >= ?", (day_ago,)).fetchone()["n"]
    completed = conn.execute("SELECT COUNT(*) AS n FROM tasks WHERE status = 'COMPLETED'").fetchone()["n"]
    failed = conn.execute("SELECT COUNT(*) AS n FROM tasks WHERE status = 'FAILED'").fetchone()["n"]
    running = conn.execute("SELECT COUNT(*) AS n FROM tasks WHERE status IN ('RUNNING','PLANNING','VERIFYING')").fetchone()["n"]
    waiting = conn.execute("SELECT COUNT(*) AS n FROM tasks WHERE status = 'WAITING_APPROVAL'").fetchone()["n"]
    online_devices = conn.execute("SELECT COUNT(*) AS n FROM devices WHERE status = 'ONLINE'").fetchone()["n"]

    success_rate = round((completed / total_tasks) * 100, 1) if total_tasks else None

    # Task durations from timestamps.
    durations_ms = []
    rows = conn.execute(
        "SELECT created_at, started_at, completed_at FROM tasks WHERE completed_at IS NOT NULL LIMIT 200"
    ).fetchall()
    for row in rows:
        start = _parse_ts(row["started_at"]) or _parse_ts(row["created_at"])
        end = _parse_ts(row["completed_at"])
        if start and end:
            durations_ms.append((end - start).total_seconds() * 1000)
    avg_duration_ms = round(sum(durations_ms) / len(durations_ms)) if durations_ms else None

    # AI error frequency (24h) from audit log.
    err_rows = conn.execute(
        "SELECT COUNT(*) AS n FROM audit_log WHERE result IN ('FAILED','ERROR') AND timestamp >= ?",
        (day_ago,),
    ).fetchone()
    error_frequency_24h = err_rows["n"]
    ai_row = conn.execute(
        "SELECT AVG(value) AS average, COUNT(*) AS samples FROM metric_events WHERE name='ai_response_latency_ms' AND timestamp >= ?",
        (day_ago,),
    ).fetchone()
    ops = conn.execute(
        """SELECT
             SUM(CASE WHEN status NOT IN ('RESOLVED','REJECTED') THEN 1 ELSE 0 END) active,
             SUM(CASE WHEN severity='CRITICAL' AND status NOT IN ('RESOLVED','REJECTED') THEN 1 ELSE 0 END) critical
           FROM ops_incidents"""
    ).fetchone()
    ops_agents = conn.execute("SELECT SUM(CASE WHEN state='RUNNING' THEN 1 ELSE 0 END) running FROM ops_agents").fetchone()
    ops_failed_runs = conn.execute("SELECT COUNT(*) n FROM ops_agent_usage WHERE status='FAILED' AND created_at >= ?", (day_ago,)).fetchone()["n"]
    ops_failed_notifications = conn.execute("SELECT COUNT(*) n FROM ops_notifications WHERE delivery_status='FAILED'").fetchone()["n"]

    return {
        "period": "24h",
        "active_users": conn.execute("SELECT COUNT(DISTINCT user_id) AS n FROM devices WHERE status = 'ONLINE'").fetchone()["n"],
        "online_devices": online_devices,
        "running_tasks": running,
        "waiting_approvals": waiting,
        "queue_length": conn.execute("SELECT COUNT(*) AS n FROM agent_jobs WHERE status IN ('PENDING','CLAIMED')").fetchone()["n"],
        "success_rate": success_rate,
        "failure_rate": round((failed / total_tasks) * 100, 1) if total_tasks else None,
        "tasks_total": total_tasks,
        "tasks_24h": day_tasks,
        "avg_task_duration_ms": avg_duration_ms,
        "error_frequency_24h": error_frequency_24h,
        "avg_ai_response_latency_ms": round(ai_row["average"]) if ai_row["average"] is not None else None,
        "ai_response_samples_24h": ai_row["samples"],
        "ops_active_incidents": ops["active"] or 0,
        "ops_critical_incidents": ops["critical"] or 0,
        "ops_running_agents": ops_agents["running"] or 0,
        "ops_failed_agent_runs_24h": ops_failed_runs,
        "ops_failed_notifications": ops_failed_notifications,
        "ops_pending_approvals": conn.execute("SELECT COUNT(*) n FROM ops_approvals WHERE status='PENDING'").fetchone()["n"],
    }


def record_metric(conn, name: str, value: float, tags: dict | None = None) -> None:
    conn.execute(
        "INSERT INTO metric_events(name,value,timestamp,tags) VALUES(?,?,?,?)",
        (name, float(value), utcnow_iso(), json.dumps(tags or {}, ensure_ascii=False)),
    )


def prometheus_metrics(conn) -> str:
    values = compute_metrics(conn)
    lines = []
    for key, value in values.items():
        if isinstance(value, (int, float)) and value is not None:
            lines.append(f"# TYPE rapiin_{key} gauge")
            lines.append(f"rapiin_{key} {value}")
    return "\n".join(lines) + "\n"
