"""Supervisor monitoring summaries (authorized, monitor-first)."""
from __future__ import annotations

from .devices import mark_stale_devices_offline
from .tasks import list_tasks


def build_monitoring_context(conn) -> dict:
    """Return a compact authorized context used by Supervisor Chat."""
    mark_stale_devices_offline(conn)

    users = conn.execute(
        "SELECT id, name, email, role, is_active FROM users WHERE role = 'USER' ORDER BY name"
    ).fetchall()
    devices = conn.execute(
        "SELECT d.id, d.device_name, d.status, d.last_heartbeat_at, u.name AS user_name "
        "FROM devices d JOIN users u ON u.id = d.user_id ORDER BY d.id DESC"
    ).fetchall()
    tasks = list_tasks(conn, limit=50)
    approvals = conn.execute(
        "SELECT a.id, a.action, a.status, a.risk, u.name AS user_name "
        "FROM approvals a JOIN users u ON u.id = a.user_id ORDER BY a.id DESC LIMIT 20"
    ).fetchall()
    activity = conn.execute(
        "SELECT actor, action, resource, timestamp, result FROM audit_log ORDER BY id DESC LIMIT 20"
    ).fetchall()

    return {
        "users": [dict(r) for r in users],
        "devices": [dict(r) for r in devices],
        "tasks": [
            {k: v for k, v in dict(r).items() if k not in {"result_json"}} for r in tasks
        ],
        "approvals": [dict(r) for r in approvals],
        "activity": [dict(r) for r in activity],
    }


def overview(conn) -> dict:
    mark_stale_devices_offline(conn)

    active_users = conn.execute(
        "SELECT COUNT(DISTINCT user_id) AS n FROM devices WHERE status = 'ONLINE'"
    ).fetchone()["n"]
    running_tasks = conn.execute("SELECT COUNT(*) AS n FROM tasks WHERE status = 'RUNNING'").fetchone()["n"]
    waiting_tasks = conn.execute("SELECT COUNT(*) AS n FROM tasks WHERE status = 'WAITING_APPROVAL'").fetchone()["n"]

    total = conn.execute("SELECT COUNT(*) AS n FROM tasks").fetchone()["n"]
    succeeded = conn.execute("SELECT COUNT(*) AS n FROM tasks WHERE status = 'COMPLETED'").fetchone()["n"]
    failed = conn.execute("SELECT COUNT(*) AS n FROM tasks WHERE status = 'FAILED'").fetchone()["n"]
    success_rate = round((succeeded / total) * 100, 1) if total else None

    failed_tasks = list_tasks(conn, status="FAILED", limit=5)
    pending_approvals = conn.execute(
        "SELECT COUNT(*) AS n FROM approvals WHERE status = 'PENDING'"
    ).fetchone()["n"]
    offline_devices = conn.execute(
        "SELECT d.device_name, u.name AS user_name FROM devices d "
        "JOIN users u ON u.id = d.user_id WHERE d.status = 'OFFLINE' LIMIT 5"
    ).fetchall()

    attention = []
    for task in failed_tasks[:2]:
        attention.append({
            "type": "task_failed",
            "title": f"Tugas {task['type']} gagal",
            "detail": f"Dimiliki oleh user #{task['user_id']}.",
            "link": f"/supervisor/task-detail.html?id={task['id']}",
        })
    if pending_approvals:
        attention.append({
            "type": "approval",
            "title": f"{pending_approvals} persetujuan menunggu",
            "detail": "Tindakan pengguna membutuhkan keputusan supervisor.",
            "link": "/supervisor/approvals.html",
        })
    for device in offline_devices:
        attention.append({
            "type": "device_offline",
            "title": f"Perangkat {device['device_name']} tidak terhubung",
            "detail": f"Milik {device['user_name']}.",
            "link": "/supervisor/employees.html",
        })

    recent_activity = conn.execute(
        "SELECT actor, action, resource, timestamp, result FROM audit_log ORDER BY id DESC LIMIT 8"
    ).fetchall()

    return {
        "status": "SEHAT" if not failed_tasks else "PERLU_PERHATIAN",
        "active_users": active_users,
        "running_tasks": running_tasks,
        "waiting_approvals": pending_approvals,
        "success_rate": success_rate,
        "failed_tasks": failed,
        "attention": attention,
        "recent_activity": [dict(r) for r in recent_activity],
    }


def employees(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT u.id AS user_id, u.name AS name, u.email, u.is_active,
               d.id AS device_id, d.device_name, d.status AS device_status,
               d.last_heartbeat_at,
               (SELECT COUNT(*) FROM tasks t WHERE t.user_id = u.id
                AND t.status IN ('RUNNING','PENDING','PLANNING','VERIFYING')) AS active_tasks
        FROM users u
        LEFT JOIN devices d ON d.user_id = u.id
        WHERE u.role = 'USER'
        ORDER BY u.name
        """
    ).fetchall()
    return [dict(r) for r in rows]


def employee_detail(conn, user_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT u.id AS user_id, u.name, u.email, u.is_active, u.created_at,
               d.id AS device_id, d.device_name, d.os, d.agent_version,
               d.status AS device_status, d.last_heartbeat_at
        FROM users u LEFT JOIN devices d ON d.user_id = u.id
        WHERE u.id = ? AND u.role = 'USER'
        """,
        (user_id,),
    ).fetchone()
    if not row:
        return None
    data = dict(row)
    data["tasks"] = list_tasks(conn, user_id=user_id, limit=10)
    recent = conn.execute(
        "SELECT actor, action, resource, timestamp, result FROM audit_log WHERE user_id = ? ORDER BY id DESC LIMIT 10",
        (user_id,),
    ).fetchall()
    data["recent_activity"] = [dict(r) for r in recent]
    return data
