"""Device agent job queue.

Server-side queue of filesystem jobs delegated to a registered Desktop Agent
(PRD section 8/11). The desktop agent polls for pending jobs, executes the
operation locally on the employee computer, and reports the result back.

Read-only jobs (scan, search, duplicate, parse, classify, index) run on the
device agent. Mutation jobs stay behind the approval flow on the server and
are only queued after approval.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone

from .audit import record_audit
from .database import connect, utcnow_iso

# Large user folders can legitimately take longer than a minute to enumerate
# and hash. The desktop agent renews its lease while it works, so the server
# must keep waiting long enough to receive that valid result.
WAIT_BUDGET_SECONDS = 180
LEASE_SECONDS = 90


def enqueue_job(
    conn,
    *,
    task_id: int | None,
    device_id: int,
    user_id: int,
    kind: str,
    payload: dict,
    idempotency_key: str | None = None,
) -> int:
    if idempotency_key:
        existing = conn.execute(
            "SELECT id FROM agent_jobs WHERE idempotency_key = ?", (idempotency_key,)
        ).fetchone()
        if existing:
            return existing["id"]
    cur = conn.execute(
        """
        INSERT INTO agent_jobs (task_id, device_id, user_id, kind, payload, status, created_at, idempotency_key)
        VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?)
        """,
        (task_id, device_id, user_id, kind, json.dumps(payload, ensure_ascii=False), utcnow_iso(), idempotency_key),
    )
    return cur.lastrowid


def claim_next_job(conn, *, device_id: int, claimed_by_key_hash: str) -> dict | None:
    """Atomically claim the oldest pending job for this device."""
    # Verify the device key belongs to this device before allowing claims.
    row = conn.execute(
        "SELECT id FROM devices WHERE id = ? AND device_key_hash = ?",
        (device_id, claimed_by_key_hash),
    ).fetchone()
    if not row:
        return None

    requeue_expired_jobs(conn, device_id=device_id)
    lease_until = (datetime.now(timezone.utc) + timedelta(seconds=LEASE_SECONDS)).isoformat()
    row = conn.execute(
        """
        UPDATE agent_jobs
        SET status = 'CLAIMED', claimed_at = ?, lease_expires_at = ?, attempt_count = attempt_count + 1
        WHERE id = (SELECT id FROM agent_jobs
                    WHERE device_id = ? AND status = 'PENDING'
                    ORDER BY id ASC LIMIT 1)
        RETURNING *
        """,
        (utcnow_iso(), lease_until, device_id),
    ).fetchone()
    return dict(row) if row else None


def requeue_expired_jobs(conn, *, device_id: int | None = None) -> int:
    """Recover jobs abandoned by a crashed/restarted agent after their lease."""
    query = """
        UPDATE agent_jobs SET status = 'PENDING', claimed_at = NULL, lease_expires_at = NULL
        WHERE status = 'CLAIMED' AND lease_expires_at IS NOT NULL AND lease_expires_at < ?
    """
    values: list = [utcnow_iso()]
    if device_id is not None:
        query += " AND device_id = ?"
        values.append(device_id)
    return conn.execute(query, values).rowcount


def get_job(conn, job_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM agent_jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def finish_job(
    conn,
    *,
    job_id: int,
    device_id: int,
    claimed_by_key_hash: str,
    status: str,
    result: dict | None = None,
    error: str | None = None,
) -> dict | None:
    if status not in {"SUCCEEDED", "FAILED"}:
        raise ValueError("Status job harus SUCCEEDED atau FAILED")
    device = conn.execute(
        "SELECT id FROM devices WHERE id = ? AND device_key_hash = ?",
        (device_id, claimed_by_key_hash),
    ).fetchone()
    if not device:
        return None
    job = get_job(conn, job_id)
    if not job or job["device_id"] != device_id:
        return None
    if job["status"] in {"SUCCEEDED", "FAILED"}:
        return job  # idempotent redelivery of the same result
    if job["status"] != "CLAIMED":
        return None
    conn.execute(
        """
        UPDATE agent_jobs SET status = ?, result_json = ?, error = ?, finished_at = ?, lease_expires_at = NULL
        WHERE id = ? AND status = 'CLAIMED'
        """,
        (status, json.dumps(result or {}, ensure_ascii=False), error, utcnow_iso(), job_id),
    )
    job = get_job(conn, job_id)
    record_audit(
        conn,
        actor="device_agent",
        actor_role="SYSTEM",
        user_id=job["user_id"],
        device_id=device_id,
        action=f"agent_job_{status.lower()}",
        resource=f"agent_job:{job_id}",
        result=status,
        error=error,
        task_id=job["task_id"],
    )
    return job


def renew_job_lease(conn, *, job_id: int, device_id: int, claimed_by_key_hash: str) -> bool:
    """Extend a claimed job lease while the agent is still processing it."""
    lease_until = (datetime.now(timezone.utc) + timedelta(seconds=LEASE_SECONDS)).isoformat()
    changed = conn.execute(
        "UPDATE agent_jobs SET lease_expires_at = ? WHERE id = ? AND device_id = ? AND status = 'CLAIMED' "
        "AND EXISTS (SELECT 1 FROM devices WHERE id = ? AND device_key_hash = ?)",
        (lease_until, job_id, device_id, device_id, claimed_by_key_hash),
    )
    return changed.rowcount == 1


def find_online_device(conn, *, device_id: int | None, user_id: int) -> dict | None:
    """Return an online device for the user, preferring the given device."""
    if device_id:
        row = conn.execute(
            "SELECT * FROM devices WHERE id = ? AND user_id = ? AND status = 'ONLINE'",
            (device_id, user_id),
        ).fetchone()
        if row:
            return dict(row)
    row = conn.execute(
        "SELECT * FROM devices WHERE user_id = ? AND status = 'ONLINE' ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    return dict(row) if row else None


def delegate_job_and_wait(conn, *, task_id, device, user_id, kind, payload, budget: int = WAIT_BUDGET_SECONDS):
    """Enqueue a job for a device agent and wait for its result.

    The current transaction is committed first so the agent sees the job.
    Returns the tool_result dict on SUCCEEDED, an error dict on FAILED, or
    None when the wait budget expires (caller should fall back to local).
    """
    # Commit so the job row is visible to the desktop agent process.
    conn.commit()
    job_id = enqueue_job(
        conn,
        task_id=task_id,
        device_id=device["id"],
        user_id=user_id,
        kind=kind,
        payload=payload,
        idempotency_key=f"task:{task_id}:tool:{kind}" if task_id else None,
    )
    conn.commit()

    poll_conn = connect()
    try:
        deadline = time.monotonic() + budget
        while time.monotonic() < deadline:
            time.sleep(1.0)
            try:
                job = get_job(poll_conn, job_id)
            except Exception:  # noqa: BLE001
                return None
            if not job:
                return None
            if job["status"] == "SUCCEEDED":
                try:
                    result = json.loads(job["result_json"] or "{}")
                except json.JSONDecodeError:
                    result = {}
                if isinstance(result, dict) and result.get("tool_result") is not None:
                    return result["tool_result"]
                return result
            if job["status"] == "FAILED":
                return {"status": "ERROR", "message": job.get("error") or "Operasi pada perangkat gagal."}
    finally:
        poll_conn.close()
    return None
