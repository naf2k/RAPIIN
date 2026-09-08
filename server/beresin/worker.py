"""Background task worker.

Long tasks (PRD sections 15, 23) run asynchronously: the HTTP request that
creates a conversation message returns immediately with a task_id, and a
daemon thread performs the Hermes agent loop against its own database
connection. The frontend polls the task status.
"""
from __future__ import annotations

import threading
import sqlite3
from datetime import datetime, timedelta, timezone

from .database import connect


def spawn_conversation_task(*, user_id: int, conversation_id: int, task_id: int, device_id: int | None) -> None:
    """Persist then dispatch a conversation job; safe across API restarts."""
    conn = connect()
    try:
        from .database import utcnow_iso
        conn.execute(
            """INSERT OR IGNORE INTO conversation_jobs
               (task_id, user_id, conversation_id, device_id, status, created_at)
               VALUES (?, ?, ?, ?, 'PENDING', ?)""",
            (task_id, user_id, conversation_id, device_id, utcnow_iso()),
        )
        conn.commit()
    finally:
        conn.close()
    thread = threading.Thread(
        target=_claim_and_run,
        kwargs={"task_id": task_id},
        name=f"beresin-task-{task_id}",
        daemon=True,
    )
    thread.start()


def _claim_and_run(*, task_id: int) -> None:
    conn = connect()
    try:
        lease = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        job = conn.execute(
            """UPDATE conversation_jobs SET status='CLAIMED', attempt_count=attempt_count+1, lease_expires_at=?
               WHERE task_id=? AND status='PENDING' RETURNING *""",
            (lease, task_id),
        ).fetchone()
        conn.commit()
    finally:
        conn.close()
    if not job:
        return
    data = dict(job)
    try:
        _run_task(user_id=data["user_id"], conversation_id=data["conversation_id"], task_id=data["task_id"], device_id=data["device_id"])
        check = connect()
        try:
            task = check.execute("SELECT status, error FROM tasks WHERE id = ?", (task_id,)).fetchone()
        finally:
            check.close()
        if task and task["status"] in {"COMPLETED", "WAITING_APPROVAL", "CANCELLED"}:
            status, error = "SUCCEEDED", None
        else:
            status, error = "FAILED", (task["error"] if task else "Task hilang setelah worker berjalan")
    except Exception as exc:  # defensive: _run_task normally records its errors
        status, error = "FAILED", str(exc)
    conn = connect()
    try:
        from .database import utcnow_iso
        conn.execute(
            "UPDATE conversation_jobs SET status=?, error=?, lease_expires_at=NULL, finished_at=? WHERE task_id=? AND status='CLAIMED'",
            (status, error, utcnow_iso(), task_id),
        )
        conn.commit()
    except sqlite3.Error:
        # The application schema is always present in production. This guard
        # prevents a daemon thread from leaking during isolated test teardown.
        conn.rollback()
    finally:
        conn.close()


def recover_conversation_jobs() -> int:
    """Requeue expired work and dispatch every persisted pending AI job."""
    from .database import utcnow_iso
    conn = connect()
    try:
        conn.execute(
            "UPDATE conversation_jobs SET status='PENDING', lease_expires_at=NULL WHERE status='CLAIMED' AND lease_expires_at < ?",
            (utcnow_iso(),),
        )
        ids = [row["task_id"] for row in conn.execute("SELECT task_id FROM conversation_jobs WHERE status='PENDING'").fetchall()]
        conn.commit()
    finally:
        conn.close()
    for pending_task_id in ids:
        threading.Thread(target=_claim_and_run, kwargs={"task_id": pending_task_id}, name=f"beresin-recovery-{pending_task_id}", daemon=True).start()
    return len(ids)


def _run_task(*, user_id: int, conversation_id: int, task_id: int, device_id: int | None) -> None:
    """Execute the conversation task in this thread (own DB connection)."""
    from .agent.core import HermesCore
    from .ai import provider as provider_mod
    from .audit import record_audit
    from .memory import add_message, get_conversation_messages, get_memory
    from .notifications import notify_task_outcome
    from .permissions import PermissionEngine
    from .tasks import get_task, update_task
    from .events import publish

    conn = connect()
    try:
        # Re-read fresh state inside the worker's own connection.
        task = get_task(conn, task_id)
        if not task:
            return
        conv_row = conn.execute(
            "SELECT id FROM conversations WHERE id = ? AND user_id = ?", (conversation_id, user_id)
        ).fetchone()
        if not conv_row:
            update_task(conn, task_id, status="FAILED", error="Percakapan tidak ditemukan.", completed=True)
            return
        user_row = conn.execute("SELECT id, name FROM users WHERE id = ?", (user_id,)).fetchone()
        user_name = user_row["name"] if user_row else str(user_id)

        update_task(conn, task_id, status="RUNNING", started=True)
        history = get_conversation_messages(conn, conversation_id, limit=40)
        memory = get_memory(conn, user_id)
        if memory:
            history.insert(0, {
                "role": "assistant",
                "content": "Konteks pribadi pengguna (jangan dibagikan): "
                           + "; ".join(f"{k}={v}" for k, v in memory.items()),
            })

        try:
            core = HermesCore(provider_mod.get_provider())
            result = core.run_user_conversation(
                conn,
                user_id=user_id,
                conversation_history=history,
                task_id=task_id,
                device_id=device_id,
                permissions=PermissionEngine.from_db(conn, role="USER"),
                on_delta=lambda text: publish(task_id, {"type": "assistant_delta", "delta": text}),
            )
        except Exception as exc:  # noqa: BLE001
            update_task(conn, task_id, status="FAILED", error=str(exc), completed=True)
            notify_task_outcome(conn, user_id=user_id, task_type="percakapan", status="FAILED", task_id=task_id, error=str(exc))
            record_audit(
                conn, actor="BERESIN", actor_role="SYSTEM", user_id=user_id, device_id=device_id,
                action="agent_error", resource=f"conversation:{conversation_id}",
                result="FAILED", error=str(exc), task_id=task_id,
            )
            conn.commit()
            return

        final = result["final_response"]
        publish(task_id, {"type": "assistant_final", "content": final})
        add_message(conn, conversation_id, "assistant", final)
        if result.get("cancelled"):
            update_task(conn, task_id, status="CANCELLED", completed=True)
            record_audit(
                conn, actor="BERESIN", actor_role="SYSTEM", user_id=user_id, device_id=device_id,
                action="task_cancelled", resource=f"task:{task_id}", result="SUCCESS", task_id=task_id,
            )
            conn.commit()
            return
        # Update title from first user message if still default.
        conn.execute(
            "UPDATE conversations SET title = COALESCE(NULLIF(title, 'Percakapan baru'), substr((SELECT content FROM messages WHERE conversation_id = ? AND role = 'user' ORDER BY id LIMIT 1), 1, 60)) WHERE id = ?",
            (conversation_id, conversation_id),
        )

        waiting = [e for e in result["tool_events"] if e["status"] in {"WAITING_USER_APPROVAL", "WAITING_SUPERVISOR_APPROVAL"}]
        if waiting:
            update_task(conn, task_id, status="WAITING_APPROVAL")
        elif any(e["status"] in {"ERROR", "BLOCKED"} for e in result["tool_events"]):
            error_message = next(
                (e.get("error") for e in result["tool_events"] if e["status"] in {"ERROR", "BLOCKED"} and e.get("error")),
                "Salah satu langkah gagal atau diblokir.",
            )
            update_task(conn, task_id, status="FAILED", error=error_message, completed=True)
            notify_task_outcome(conn, user_id=user_id, task_type="percakapan", status="FAILED", task_id=task_id, error=error_message)
        else:
            update_task(conn, task_id, status="VERIFYING", progress=99)
            update_task(conn, task_id, status="COMPLETED", progress=100, completed=True, result={"tool_events": result["tool_events"]})
            notify_task_outcome(conn, user_id=user_id, task_type="percakapan", status="COMPLETED", task_id=task_id)

        record_audit(
            conn, actor="BERESIN", actor_role="SYSTEM", user_id=user_id, device_id=device_id,
            action="assistant_reply", resource=f"conversation:{conversation_id}", task_id=task_id,
        )
        conn.commit()
    except Exception:  # noqa: BLE001 - never let a worker thread die silently
        conn.rollback()
    finally:
        conn.close()
