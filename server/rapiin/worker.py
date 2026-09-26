"""Background task worker.

Long tasks (PRD sections 15, 23) run asynchronously: the HTTP request that
creates a conversation message returns immediately with a task_id, and a
daemon thread performs the Hermes agent loop against its own database
connection. The frontend polls the task status.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

from .database import connect, is_transient_db_error

# A long AI turn can outlive a short lease. The in-process registry keeps a
# periodic sweep from requeuing a task that is still running here, and the
# generous lease covers a worker that lives in a separate process.
CONVERSATION_LEASE_MINUTES = 30
MAX_CONVERSATION_REQUEUES = 3
_RUNNING_TASKS: set[int] = set()
_RUNNING_LOCK = threading.Lock()


def _safe_close(conn) -> None:
    """Close without raising: a dead connection is already unusable."""
    try:
        conn.close()
    except Exception:  # noqa: BLE001
        pass


def _retry_transient(fn, *, attempts: int = 5, base_delay: float = 0.5):
    """Run ``fn``, retrying only connection-level failures with backoff."""
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            if not is_transient_db_error(exc) or attempt == attempts - 1:
                raise
            time.sleep(base_delay * (attempt + 1))
    raise AssertionError("unreachable")


def spawn_conversation_task(*, user_id: int, conversation_id: int, task_id: int, device_id: int | None) -> None:
    """Persist then dispatch a conversation job; safe across API restarts."""
    conn = connect()
    try:
        from .database import utcnow_iso
        conn.execute(
            """INSERT INTO conversation_jobs
               (task_id, user_id, conversation_id, device_id, status, created_at)
               VALUES (?, ?, ?, ?, 'PENDING', ?) ON CONFLICT(task_id) DO NOTHING""",
            (task_id, user_id, conversation_id, device_id, utcnow_iso()),
        )
        conn.commit()
    finally:
        conn.close()
    from .queue_backend import enqueue_conversation_task
    if enqueue_conversation_task(task_id):
        return
    thread = threading.Thread(
        target=_claim_and_run,
        kwargs={"task_id": task_id},
        name=f"rapiin-task-{task_id}",
        daemon=True,
    )
    thread.start()


def _dispatch_conversation_task(task_id: int) -> None:
    """Hand a task to Redis when available, otherwise run it in this process."""
    from .queue_backend import enqueue_conversation_task
    if enqueue_conversation_task(task_id):
        return
    threading.Thread(
        target=_claim_and_run,
        kwargs={"task_id": task_id},
        name=f"rapiin-recovery-{task_id}",
        daemon=True,
    ).start()


def _task_status(task_id: int):
    conn = connect()
    try:
        return conn.execute("SELECT status, error FROM tasks WHERE id = ?", (task_id,)).fetchone()
    finally:
        _safe_close(conn)


def _write_conversation_job(task_id: int, sql: str, params: tuple) -> None:
    """Apply a bookkeeping write, retrying a dropped connection."""
    def _update():
        conn = connect()
        try:
            conn.execute(sql, params)
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001
                pass
            raise
        finally:
            _safe_close(conn)
    try:
        _retry_transient(_update)
    except Exception:  # noqa: BLE001
        # Never let a daemon thread die on a bookkeeping write; the recovery
        # sweep reconciles the job on its next tick.
        pass


def _finish_conversation_job(task_id: int, status: str, error: str | None) -> None:
    from .database import utcnow_iso
    _write_conversation_job(
        task_id,
        "UPDATE conversation_jobs SET status=?, error=?, lease_expires_at=NULL, finished_at=? WHERE task_id=? AND status='CLAIMED'",
        (status, error, utcnow_iso(), task_id),
    )


def _requeue_conversation_job(task_id: int) -> None:
    _write_conversation_job(
        task_id,
        "UPDATE conversation_jobs SET status='PENDING', lease_expires_at=NULL WHERE task_id=? AND status='CLAIMED'",
        (task_id,),
    )


def _claim_and_run(*, task_id: int) -> None:
    conn = connect()
    try:
        lease = (datetime.now(timezone.utc) + timedelta(minutes=CONVERSATION_LEASE_MINUTES)).isoformat()
        job = conn.execute(
            """UPDATE conversation_jobs SET status='CLAIMED', attempt_count=attempt_count+1, lease_expires_at=?
               WHERE task_id=? AND status='PENDING' RETURNING *""",
            (lease, task_id),
        ).fetchone()
        conn.commit()
    finally:
        _safe_close(conn)
    if not job:
        return
    data = dict(job)
    with _RUNNING_LOCK:
        _RUNNING_TASKS.add(task_id)
    try:
        try:
            outcome = _run_task(
                user_id=data["user_id"],
                conversation_id=data["conversation_id"],
                task_id=data["task_id"],
                device_id=data["device_id"],
            ) or "DONE"
        except Exception as exc:  # defensive: _run_task normally records its errors
            outcome = "REQUEUE" if is_transient_db_error(exc) else "FAILED"
            if outcome == "FAILED":
                _finish_conversation_job(task_id, "FAILED", str(exc))
                return

        if outcome == "REQUEUE":
            if int(data.get("attempt_count") or 0) >= MAX_CONVERSATION_REQUEUES:
                # The connection kept dying. Give the user a real answer rather
                # than looping forever.
                _mark_task_failed(task_id, "Koneksi database terputus berulang; task dihentikan.")
                _finish_conversation_job(task_id, "FAILED", "Koneksi database terputus berulang.")
            else:
                _requeue_conversation_job(task_id)
            return

        try:
            task = _retry_transient(lambda: _task_status(task_id))
        except Exception as exc:  # noqa: BLE001
            if is_transient_db_error(exc):
                _requeue_conversation_job(task_id)
                return
            raise
        if task and task["status"] in {"COMPLETED", "WAITING_APPROVAL", "CANCELLED"}:
            _finish_conversation_job(task_id, "SUCCEEDED", None)
        else:
            _finish_conversation_job(task_id, "FAILED", (task["error"] if task else "Task hilang setelah worker berjalan"))
    finally:
        with _RUNNING_LOCK:
            _RUNNING_TASKS.discard(task_id)


def _mark_task_failed(task_id: int, message: str) -> None:
    from .database import utcnow_iso

    def _update():
        conn = connect()
        try:
            conn.execute(
                "UPDATE tasks SET status='FAILED', error=?, completed_at=? WHERE id = ?",
                (message, utcnow_iso(), task_id),
            )
            conn.commit()
        finally:
            _safe_close(conn)
    try:
        _retry_transient(_update)
    except Exception:  # noqa: BLE001
        pass


def _expired_claim_ids() -> list[int]:
    """Task ids whose CLAIMED lease has lapsed (read-only)."""
    from .database import utcnow_iso
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT task_id FROM conversation_jobs "
            "WHERE status='CLAIMED' AND (lease_expires_at IS NULL OR lease_expires_at < ?)",
            (utcnow_iso(),),
        ).fetchall()
    finally:
        _safe_close(conn)
    return [row["task_id"] for row in rows]


def _reclaim_claim(task_id: int) -> bool:
    """Flip one expired CLAIMED job back to PENDING. True when it changed."""
    from .database import utcnow_iso

    def _update():
        conn = connect()
        try:
            cur = conn.execute(
                "UPDATE conversation_jobs SET status='PENDING', lease_expires_at=NULL "
                "WHERE task_id=? AND status='CLAIMED' AND (lease_expires_at IS NULL OR lease_expires_at < ?)",
                (task_id, utcnow_iso()),
            )
            conn.commit()
            return cur.rowcount == 1
        finally:
            _safe_close(conn)
    return bool(_retry_transient(_update))


def requeue_stale_conversation_jobs() -> int:
    """Resume work interrupted by host sleep/wake or a database restart.

    Runs from the periodic monitor so a dropped connection cannot strand a task
    until the next server restart. A healthy in-flight task holds a far-future
    lease, and a task running in this process is skipped explicitly, so an
    active job is never flipped back to PENDING (which would double-run it).
    """
    with _RUNNING_LOCK:
        running = set(_RUNNING_TASKS)
    recovered = 0
    for task_id in _expired_claim_ids():
        if task_id in running:
            continue
        if _reclaim_claim(task_id):
            _dispatch_conversation_task(task_id)
            recovered += 1
    return recovered


def recover_conversation_jobs() -> int:
    """Requeue expired work and dispatch every persisted pending AI job."""
    with _RUNNING_LOCK:
        running = set(_RUNNING_TASKS)
    for task_id in _expired_claim_ids():
        if task_id not in running:
            _reclaim_claim(task_id)
    conn = connect()
    try:
        pending = [row["task_id"] for row in conn.execute("SELECT task_id FROM conversation_jobs WHERE status='PENDING'").fetchall()]
    finally:
        _safe_close(conn)
    for pending_task_id in pending:
        if pending_task_id not in running:
            _dispatch_conversation_task(pending_task_id)
    return len(pending)


def run_queue_worker(stop_event=None) -> None:
    """Consume Redis hints; atomic database claims prevent duplicate execution."""
    import json
    import logging
    import time

    from .database import utcnow_iso
    from .queue_backend import dequeue_conversation_task

    logger = logging.getLogger(__name__)
    while not (stop_event and stop_event.is_set()):
        try:
            conn = connect()
            try:
                now = utcnow_iso()
                conn.execute(
                    "INSERT INTO ops_policies(key,value_json,updated_at) VALUES(?,?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",
                    ("worker.conversation.heartbeat", json.dumps({"at": now}), now),
                )
                conn.commit()
            finally:
                conn.close()
            task_id = dequeue_conversation_task(timeout=2)
            if task_id is not None:
                _claim_and_run(task_id=task_id)
        except Exception as exc:  # noqa: BLE001 - a transient outage must not kill the worker
            if is_transient_db_error(exc):
                # Host sleep/wake or a database restart: reconnect on the next
                # tick instead of flooding the log with stack traces.
                logger.warning("Queue worker connection lost; retrying: %s", exc)
                time.sleep(2)
            else:
                logger.exception("Queue worker poll failed; retrying")
                time.sleep(1)
        if stop_event:
            time.sleep(0.05)


def main() -> int:
    """Entry point for a standalone queue worker process (`python -m rapiin.worker`)."""
    from .config import settings

    if not settings.rapiin_redis_url:
        raise SystemExit("RAPIIN_REDIS_URL wajib dikonfigurasi untuk worker terpisah.")
    try:
        run_queue_worker()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _run_task(*, user_id: int, conversation_id: int, task_id: int, device_id: int | None) -> None:
    """Execute the conversation task in this thread (own DB connection)."""
    from .agent.core import HermesCore
    from .ai import provider as provider_mod
    from .audit import record_audit
    from .events import publish
    from .memory import add_message, get_conversation_messages, get_memory
    from .notifications import notify_task_outcome
    from .permissions import PermissionEngine
    from .tasks import get_task, update_task

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

        # Persist RUNNING before the potentially slow provider request. The
        # Hermes loop also commits before every subsequent provider turn.
        conn.commit()

        try:
            core = HermesCore(provider_mod.get_provider())
            result = core.run_user_conversation(
                conn,
                user_id=user_id,
                conversation_history=history,
                task_id=task_id,
                device_id=device_id,
                permissions=PermissionEngine.from_db(conn, role="USER", user_id=user_id),
                on_delta=lambda text: publish(task_id, {"type": "assistant_delta", "delta": text}),
            )
        except Exception as exc:  # noqa: BLE001
            if is_transient_db_error(exc):
                # Connection lost mid-turn: the work is interrupted, not wrong.
                # Let the recovery sweep requeue it instead of latching FAILED.
                return "REQUEUE"
            update_task(conn, task_id, status="FAILED", error=str(exc), completed=True)
            notify_task_outcome(conn, user_id=user_id, task_type="percakapan", status="FAILED", task_id=task_id, error=str(exc))
            record_audit(
                conn, actor="RAPIIN", actor_role="SYSTEM", user_id=user_id, device_id=device_id,
                action="agent_error", resource=f"conversation:{conversation_id}",
                result="FAILED", error=str(exc), task_id=task_id,
            )
            conn.commit()
            return "DONE"

        final = result["final_response"]
        waiting = [e for e in result["tool_events"] if e["status"] in {"WAITING_USER_APPROVAL", "WAITING_SUPERVISOR_APPROVAL"}]
        # If the user already decided the approval card while the model was
        # still finishing, the decision path owns the outcome message. Writing
        # the stale "menunggu persetujuan" answer here would land *after* the
        # confirmation ("sudah dijalankan" / "ditolak") and mislead the user.
        approvals_decided = False
        if waiting and task_id:
            rows = conn.execute("SELECT status FROM approvals WHERE task_id = ?", (task_id,)).fetchall()
            approvals_decided = bool(rows) and not any(r["status"] == "PENDING" for r in rows)
        if not approvals_decided:
            publish(task_id, {"type": "assistant_final", "content": final})
            add_message(conn, conversation_id, "assistant", final)
        if result.get("cancelled"):
            update_task(conn, task_id, status="CANCELLED", completed=True)
            record_audit(
                conn, actor="RAPIIN", actor_role="SYSTEM", user_id=user_id, device_id=device_id,
                action="task_cancelled", resource=f"task:{task_id}", result="SUCCESS", task_id=task_id,
            )
            conn.commit()
            return
        # Update title from first user message if still default.
        conn.execute(
            "UPDATE conversations SET title = COALESCE(NULLIF(title, 'Percakapan baru'), substr((SELECT content FROM messages WHERE conversation_id = ? AND role = 'user' ORDER BY id LIMIT 1), 1, 60)) WHERE id = ?",
            (conversation_id, conversation_id),
        )

        if approvals_decided:
            # Decided out-of-band: the approval path already set the final
            # status (COMPLETED / CANCELLED) and posted the outcome message.
            pass
        elif waiting:
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
            # error="" clears any stale message a mid-turn device tool may have
            # left when it briefly reported a sub-status failure.
            update_task(conn, task_id, status="COMPLETED", progress=100, completed=True, result={"tool_events": result["tool_events"]}, error="")
            notify_task_outcome(conn, user_id=user_id, task_type="percakapan", status="COMPLETED", task_id=task_id)

        record_audit(
            conn, actor="RAPIIN", actor_role="SYSTEM", user_id=user_id, device_id=device_id,
            action="assistant_reply", resource=f"conversation:{conversation_id}", task_id=task_id,
        )
        conn.commit()
        return "DONE"
    except Exception as exc:  # noqa: BLE001 - never let a worker thread die silently
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        if is_transient_db_error(exc):
            return "REQUEUE"
        raise
    finally:
        _safe_close(conn)
