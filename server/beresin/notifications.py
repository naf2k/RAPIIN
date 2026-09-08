"""Notifications for users and supervisors (PRD 6.12, 30).

V1: task completed -> success notification; important errors -> error
notification. Supervisor gets system-level notifications (device offline,
approval waiting, failed task).
"""
from __future__ import annotations

from .database import utcnow_iso


def notify(
    conn,
    *,
    user_id: int,
    role: str,
    title: str,
    body: str | None = None,
    type: str = "info",
    task_id: int | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO notifications (user_id, role, title, body, type, is_read, created_at, task_id)
        VALUES (?, ?, ?, ?, ?, 0, ?, ?)
        """,
        (user_id, role, title, body, type, utcnow_iso(), task_id),
    )
    return cur.lastrowid


def notify_task_outcome(conn, *, user_id: int, task_type: str, status: str, task_id: int, error: str | None = None) -> None:
    """Create the user + supervisor notification for a finished task."""
    if status == "COMPLETED":
        notify(
            conn,
            user_id=user_id,
            role="USER",
            title="Tugas selesai",
            body=f"Task {task_type} berhasil diselesaikan.",
            type="success",
            task_id=task_id,
        )
    elif status == "FAILED":
        notify(
            conn,
            user_id=user_id,
            role="USER",
            title="Tugas gagal",
            body=error or f"Task {task_type} tidak dapat diselesaikan.",
            type="error",
            task_id=task_id,
        )
        notify(
            conn,
            user_id=user_id,
            role="SUPERVISOR",
            title="Task gagal",
            body=f"Task {task_type} milik user #{user_id} gagal: {error or 'unknown'}",
            type="error",
            task_id=task_id,
        )


def notify_approval_waiting(conn, *, user_id: int, approval_id: int, task_id: int | None) -> None:
    notify(
        conn,
        user_id=user_id,
        role="SUPERVISOR",
        title="Persetujuan menunggu",
        body=f"Approval #{approval_id} membutuhkan keputusan supervisor.",
        type="warning",
        task_id=task_id,
    )


def list_for_user(conn, user_id: int, role: str, limit: int = 30) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, title, body, type, is_read, created_at, task_id FROM notifications
        WHERE user_id = ? AND role = ?
        ORDER BY id DESC LIMIT ?
        """,
        (user_id, role, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def mark_read(conn, notification_id: int, user_id: int) -> bool:
    cur = conn.execute(
        "UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?",
        (notification_id, user_id),
    )
    return cur.rowcount > 0


def unread_count(conn, user_id: int, role: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM notifications WHERE user_id = ? AND role = ? AND is_read = 0",
        (user_id, role),
    ).fetchone()
    return row["n"]
