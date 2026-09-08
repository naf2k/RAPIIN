"""Task Engine - create, update and list async tasks."""
from __future__ import annotations

import json

from .database import utcnow_iso

VALID_STATUSES = {
    "PENDING", "PLANNING", "WAITING_APPROVAL", "RUNNING",
    "VERIFYING", "COMPLETED", "FAILED", "CANCELLED",
}


def create_task(conn, *, user_id: int, device_id: int | None, type: str, status: str = "PENDING") -> int:
    cur = conn.execute(
        "INSERT INTO tasks (user_id, device_id, type, status, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, device_id, type, status, utcnow_iso()),
    )
    return cur.lastrowid


def update_task(
    conn,
    task_id: int,
    *,
    status: str | None = None,
    progress: float | None = None,
    processed_count: int | None = None,
    total_count: int | None = None,
    result: object = None,
    error: str | None = None,
    approval_status: str | None = None,
    started: bool = False,
    completed: bool = False,
) -> None:
    sets: list[str] = []
    values: list = []
    if status is not None:
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid task status: {status}")
        sets.append("status = ?")
        values.append(status)
    if progress is not None:
        sets.append("progress = ?")
        values.append(progress)
    if processed_count is not None:
        sets.append("processed_count = ?")
        values.append(max(0, processed_count))
    if total_count is not None:
        sets.append("total_count = ?")
        values.append(max(0, total_count))
    if result is not None:
        sets.append("result_json = ?")
        values.append(json.dumps(result, ensure_ascii=False))
    if error is not None:
        sets.append("error = ?")
        values.append(error)
    if approval_status is not None:
        sets.append("approval_status = ?")
        values.append(approval_status)
    if started:
        sets.append("started_at = ?")
        values.append(utcnow_iso())
    if completed:
        sets.append("completed_at = ?")
        values.append(utcnow_iso())
    if not sets:
        return
    values.append(task_id)
    # Column fragments come only from the fixed branches above; user input is
    # always passed through placeholders.
    conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", values)  # nosec B608
    try:
        from .events import publish
        current = get_task(conn, task_id)
        if current:
            publish(task_id, {
                "type": "progress", "task_id": task_id,
                "status": current["status"], "progress": current["progress"],
                "processed_count": current.get("processed_count", 0),
                "total_count": current.get("total_count", 0),
            })
    except Exception:
        pass


def get_task(conn, task_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return dict(row) if row else None


def list_tasks(conn, *, user_id: int | None = None, status: str | None = None, limit: int = 100) -> list[dict]:
    query = "SELECT * FROM tasks"
    clauses: list[str] = []
    values: list = []
    if user_id is not None:
        clauses.append("user_id = ?")
        values.append(user_id)
    if status:
        clauses.append("status = ?")
        values.append(status)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY id DESC LIMIT ?"
    values.append(limit)
    rows = conn.execute(query, values).fetchall()
    return [dict(row) for row in rows]


def list_task_activities(conn, task_id: int, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, actor, actor_role, action, resource, timestamp, result, error
        FROM audit_log WHERE task_id = ? ORDER BY id DESC LIMIT ?
        """,
        (task_id, limit),
    ).fetchall()
    return [dict(row) for row in rows]
