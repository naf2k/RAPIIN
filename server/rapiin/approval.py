"""Approval Engine - creates and resolves approval requests.

When an approval is APPROVED and it gates a stored tool action, the engine
executes that action immediately (PRD section 18: approval then execute).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import threading
from datetime import datetime, timedelta, timezone

from .audit import record_audit
from .database import utcnow_iso

# Serializes the lookup-then-insert in create_approval within one process.
# A partial UNIQUE index (see database.py) is the backstop for cross-process
# races: on conflict we re-select the winner instead of failing.
_CREATE_LOCK = threading.Lock()


def _snapshot_digest(tool_name: str | None, serialized_args: str) -> str:
    from .config import settings
    return hmac.new(
        settings.rapiin_secret_key.encode(),
        f"{tool_name or ''}\n{serialized_args}".encode(),
        hashlib.sha256,
    ).hexdigest()


def find_reusable_approval(
    conn,
    *,
    user_id: int,
    kind: str,
    tool_name: str | None,
    tool_args: dict | None,
    task_id: int | None = None,
    any_task: bool = False,
) -> int | None:
    """Return the id of an identical PENDING approval, if one exists.

    With ``any_task=False`` (default) the task must match too — this covers
    the agent loop emitting the same tool twice for one task. With
    ``any_task=True`` the task is ignored, which covers double-submits from
    the UI where each click mints its own task row. COALESCE keeps the lookup
    portable across SQLite/PostgreSQL.
    """
    serialized_args = json.dumps(tool_args or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    snapshot_hash = _snapshot_digest(tool_name, serialized_args)
    now = utcnow_iso()
    query = (
        "SELECT id FROM approvals WHERE user_id = ? AND kind = ? AND status = 'PENDING' "
        "AND COALESCE(tool_name, '') = COALESCE(?, '') "
        "AND COALESCE(snapshot_hash, '') = ? "
        "AND (expires_at IS NULL OR expires_at > ?) "
    )
    params: list = [user_id, kind, tool_name or "", snapshot_hash, now]
    if not any_task:
        query += "AND COALESCE(task_id, -1) = COALESCE(?, -1) "
        params.append(task_id if task_id is not None else -1)
    query += "ORDER BY id ASC LIMIT 1"
    row = conn.execute(query, params).fetchone()
    return row["id"] if row else None


def create_approval(
    conn,
    *,
    task_id: int | None,
    user_id: int,
    requested_by: str,
    kind: str,
    action: str,
    scope: str | None = None,
    risk: str | None = None,
    tool_name: str | None = None,
    tool_args: dict | None = None,
) -> int:
    serialized_args = json.dumps(tool_args or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    snapshot_hash = _snapshot_digest(tool_name, serialized_args)
    # Reuse an identical pending approval instead of showing a duplicate card.
    # A second card for the same operation is misleading: approving both fails
    # the second execution, and rejecting one cancels a task that may already
    # have run.
    approval_id: int | None = None
    with _CREATE_LOCK:
        existing_id = find_reusable_approval(
            conn, user_id=user_id, kind=kind, tool_name=tool_name, tool_args=tool_args, task_id=task_id,
        )
        if existing_id is None:
            expires_at = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
            try:
                cur = conn.execute(
                    """
                    INSERT INTO approvals (task_id, user_id, requested_by, kind, action, scope, risk,
                                           tool_name, tool_args, snapshot_hash, expires_at, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
                    """,
                    (task_id, user_id, requested_by, kind, action, scope, risk,
                     tool_name, serialized_args, snapshot_hash, expires_at, utcnow_iso()),
                )
                approval_id = cur.lastrowid
            except Exception:
                # Lost a race with an identical request, or an expired twin is
                # blocking the unique index: sweep expired twins for this
                # identity (mirroring the auto-reject of expired approvals)
                # and retry the insert once.
                existing_id = find_reusable_approval(
                    conn, user_id=user_id, kind=kind, tool_name=tool_name,
                    tool_args=tool_args, task_id=task_id,
                )
                if existing_id is None:
                    conn.execute(
                        "UPDATE approvals SET status='REJECTED', decided_at=? "
                        "WHERE user_id=? AND kind=? AND status='PENDING' "
                        "AND COALESCE(task_id,-1)=COALESCE(?,-1) "
                        "AND COALESCE(tool_name,'')=COALESCE(?,'') "
                        "AND COALESCE(snapshot_hash,'')=? "
                        "AND expires_at IS NOT NULL AND expires_at <= ?",
                        (utcnow_iso(), user_id, kind,
                         task_id if task_id is not None else -1,
                         tool_name or "", snapshot_hash, utcnow_iso()),
                    )
                    cur = conn.execute(
                        """
                        INSERT INTO approvals (task_id, user_id, requested_by, kind, action, scope, risk,
                                               tool_name, tool_args, snapshot_hash, expires_at, status, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
                        """,
                        (task_id, user_id, requested_by, kind, action, scope, risk,
                         tool_name, serialized_args, snapshot_hash, expires_at, utcnow_iso()),
                    )
                    approval_id = cur.lastrowid
        if existing_id is not None:
            record_audit(
                conn,
                actor=requested_by,
                actor_role="SYSTEM",
                user_id=user_id,
                action="approval_reused",
                resource=f"approval:{existing_id}",
                result="PENDING",
                approval_id=existing_id,
                task_id=task_id,
            )
            return existing_id
    assert approval_id is not None
    conn.execute("UPDATE tasks SET status = 'WAITING_APPROVAL', approval_status = 'PENDING' WHERE id = ?", (task_id,))
    approval_id = cur.lastrowid
    record_audit(
        conn,
        actor=requested_by,
        actor_role="SYSTEM",
        user_id=user_id,
        action="approval_requested",
        resource=f"approval:{approval_id}",
        result="PENDING",
        approval_id=approval_id,
        task_id=task_id,
    )
    return approval_id


def get_approval(conn, approval_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
    return dict(row) if row else None


def respond_approval(
    conn,
    approval_id: int,
    *,
    decision: str,
    decided_by_id: int,
    decided_by_name: str,
    decided_by_role: str,
) -> dict:
    """Approve or reject an approval. Decision must be APPROVED or REJECTED."""
    if decision not in {"APPROVED", "REJECTED"}:
        raise ValueError("Decision harus APPROVED atau REJECTED")

    approval = get_approval(conn, approval_id)
    if not approval:
        raise ValueError("Approval tidak ditemukan")
    if approval["status"] != "PENDING":
        raise ValueError("Approval sudah diputuskan")
    if approval.get("expires_at") and approval["expires_at"] < utcnow_iso():
        conn.execute("UPDATE approvals SET status='REJECTED', decided_at=? WHERE id=? AND status='PENDING'", (utcnow_iso(), approval_id))
        raise ValueError("Approval sudah kedaluwarsa. Buat review baru.")
    serialized = approval.get("tool_args") or "{}"
    expected_hash = _snapshot_digest(approval.get("tool_name"), serialized)
    if approval.get("snapshot_hash") and not hmac.compare_digest(expected_hash, approval["snapshot_hash"]):
        raise ValueError("Snapshot approval berubah dan tidak aman dieksekusi.")

    now = utcnow_iso()
    changed = conn.execute(
        "UPDATE approvals SET status = ?, decided_by = ?, decided_at = ? WHERE id = ? AND status = 'PENDING'",
        (decision, decided_by_id, now, approval_id),
    )
    if changed.rowcount != 1:
        raise ValueError("Approval sudah diputuskan")

    task_id = approval["task_id"]
    if decision == "APPROVED":
        if task_id:
            conn.execute(
                "UPDATE tasks SET status = 'RUNNING', approval_status = 'APPROVED', started_at = ? WHERE id = ?",
                (now, task_id),
            )
        _execute_approved_action(conn, approval)
    else:
        if task_id:
            conn.execute(
                "UPDATE tasks SET status = 'CANCELLED', approval_status = 'REJECTED', completed_at = ? WHERE id = ?",
                (now, task_id),
            )

    record_audit(
        conn,
        actor=decided_by_name,
        actor_role=decided_by_role,
        user_id=approval["user_id"],
        action=f"approval_{decision.lower()}",
        resource=f"approval:{approval_id}",
        result="SUCCESS",
        approval_id=approval_id,
        task_id=task_id,
    )
    return get_approval(conn, approval_id)


def _execute_approved_action(conn, approval: dict) -> None:
    """Run the stored tool once the approval is granted."""
    tool_name = approval.get("tool_name")
    if not tool_name:
        return
    try:
        tool_args = json.loads(approval.get("tool_args") or "{}")
    except json.JSONDecodeError:
        tool_args = {}

    from .tasks import get_task

    task_id = approval["task_id"]
    task = get_task(conn, task_id) if task_id else None
    user_id = approval["user_id"]
    device_id = task["device_id"] if task else None

    record_audit(
        conn,
        actor="RAPIIN",
        actor_role="SYSTEM",
        user_id=user_id,
        device_id=device_id,
        action="approval_executing",
        resource=f"approval:{approval['id']}",
        approval_id=approval["id"],
        task_id=task_id,
    )

    try:
        # Mutations must run on the employee's selected Desktop Agent. Running
        # them against the server filesystem would violate the reviewed scope.
        from .agent_jobs import enqueue_job, find_online_device

        device = find_online_device(conn, device_id=device_id, user_id=user_id)
        if not device:
            raise RuntimeError("Desktop Agent tujuan sedang offline. Tidak ada perubahan file yang dijalankan.")
        enqueue_job(
            conn,
            task_id=task_id,
            device_id=device["id"],
            user_id=user_id,
            kind=tool_name,
            payload={"tool": tool_name, "arguments": tool_args},
            idempotency_key=f"approval:{approval['id']}",
        )
        # Completion is reported asynchronously by /api/agent/result. Keeping
        # the task RUNNING avoids holding an HTTP approval request open.
    except Exception as exc:  # noqa: BLE001
        if task_id:
            conn.execute(
                "UPDATE tasks SET status = 'FAILED', error = ?, completed_at = ? WHERE id = ?",
                (str(exc), now_iso(), task_id),
            )
        record_audit(
            conn,
            actor="RAPIIN",
            actor_role="SYSTEM",
            user_id=user_id,
            device_id=device_id,
            action="approval_execution_failed",
            resource=f"approval:{approval['id']}",
            result="FAILED",
            error=str(exc),
            approval_id=approval["id"],
            task_id=task_id,
        )


def now_iso() -> str:
    return utcnow_iso()


def pending_approvals_for_user(conn, user_id: int) -> list[dict]:
    conn.execute(
        "UPDATE approvals SET status='REJECTED', decided_at=? WHERE user_id=? AND status='PENDING' AND expires_at IS NOT NULL AND expires_at < ?",
        (utcnow_iso(), user_id, utcnow_iso()),
    )
    rows = conn.execute(
        "SELECT * FROM approvals WHERE user_id = ? AND status = 'PENDING' ORDER BY id DESC", (user_id,)
    ).fetchall()
    return [dict(row) for row in rows]


def all_pending_approvals(conn, *, include_decided: bool = False, limit: int = 200) -> list[dict]:
    """Pending approvals, optionally together with the decision history.

    The supervisor console has a "done" view, so the same sweep that expires
    stale requests can also return what has already been decided.
    """
    conn.execute(
        "UPDATE approvals SET status='REJECTED', decided_at=? WHERE status='PENDING' AND expires_at IS NOT NULL AND expires_at < ?",
        (utcnow_iso(), utcnow_iso()),
    )
    if include_decided:
        rows = conn.execute(
            "SELECT * FROM approvals ORDER BY CASE status WHEN 'PENDING' THEN 0 ELSE 1 END, id DESC LIMIT ?",
            (max(1, min(limit, 1000)),),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM approvals WHERE status = 'PENDING' ORDER BY id DESC"
        ).fetchall()
    return [dict(row) for row in rows]
