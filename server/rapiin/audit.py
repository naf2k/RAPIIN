"""Append-only, hash-chained audit log."""
import hashlib
import json

from .database import utcnow_iso

FIELDS = ("actor", "actor_role", "user_id", "device_id", "action", "resource", "timestamp", "result", "error", "approval_id", "task_id")


def _event_hash(previous_hash: str, values: dict) -> str:
    canonical = json.dumps({key: values.get(key) for key in FIELDS}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256((previous_hash + canonical).encode()).hexdigest()


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
    timestamp = utcnow_iso()
    previous = conn.execute("SELECT event_hash FROM audit_log WHERE event_hash IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
    previous_hash = previous["event_hash"] if previous else "0" * 64
    values = dict(actor=actor, actor_role=actor_role, user_id=user_id, device_id=device_id,
                  action=action, resource=resource, timestamp=timestamp, result=result,
                  error=error, approval_id=approval_id, task_id=task_id)
    event_hash = _event_hash(previous_hash, values)
    cur = conn.execute(
        """
        INSERT INTO audit_log
            (actor, actor_role, user_id, device_id, action, resource,
             timestamp, result, error, approval_id, task_id, previous_hash, event_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            actor,
            actor_role,
            user_id,
            device_id,
            action,
            resource,
            timestamp,
            result,
            error,
            approval_id,
            task_id,
            previous_hash,
            event_hash,
        ),
    )
    return cur.lastrowid


def backfill_audit_chain(conn) -> int:
    previous_hash = "0" * 64
    changed = 0
    for row in conn.execute("SELECT * FROM audit_log ORDER BY id").fetchall():
        expected = _event_hash(previous_hash, {key: row[key] for key in FIELDS})
        if row["event_hash"] is None:
            conn.execute("UPDATE audit_log SET previous_hash=?,event_hash=? WHERE id=?", (previous_hash, expected, row["id"]))
            changed += 1
            previous_hash = expected
        else:
            previous_hash = row["event_hash"]
    return changed


def verify_audit_chain(conn) -> dict:
    previous_hash = "0" * 64
    count = 0
    for row in conn.execute("SELECT * FROM audit_log ORDER BY id").fetchall():
        expected = _event_hash(previous_hash, {key: row[key] for key in FIELDS})
        if row["previous_hash"] != previous_hash or row["event_hash"] != expected:
            return {"valid": False, "count": count, "broken_at": row["id"]}
        previous_hash = expected
        count += 1
    return {"valid": True, "count": count, "head_hash": previous_hash}
