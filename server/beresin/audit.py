"""Append-only audit log. Every important action is recorded here."""
from .database import utcnow_iso


def record_audit(
    conn,
    *,
    actor: str | None = None,
    actor_role: str | None = None,
    user_id: int | None = None,
    device_id: int | None = None,
    action: str,
    resource: str | None = None,
    result: str = "SUCCESS",
    error: str | None = None,
    approval_id: int | None = None,
    task_id: int | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO audit_log
            (actor, actor_role, user_id, device_id, action, resource,
             timestamp, result, error, approval_id, task_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            actor,
            actor_role,
            user_id,
            device_id,
            action,
            resource,
            utcnow_iso(),
            result,
            error,
            approval_id,
            task_id,
        ),
    )
    return cur.lastrowid
