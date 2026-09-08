"""Device Manager - registration, heartbeat and online/offline tracking."""
from __future__ import annotations

import hashlib
import os
import json
from datetime import datetime, timezone

from .audit import record_audit
from .database import utcnow_iso

HEARTBEAT_GRACE_SECONDS = 90


def _hash_device_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def register_device(
    conn,
    *,
    user_id: int,
    device_name: str,
    os_name: str | None,
    agent_version: str | None,
    capabilities: str | None = None,
    workspace_root: str | None = None,
) -> dict:
    device_key = os.urandom(32).hex()
    key_hash = _hash_device_key(device_key)
    cur = conn.execute(
        """
        INSERT INTO devices (user_id, device_name, device_key_hash, os, agent_version, status,
                             last_heartbeat_at, capabilities, workspace_root, created_at)
        VALUES (?, ?, ?, ?, ?, 'ONLINE', ?, ?, ?, ?)
        """,
        (user_id, device_name, key_hash, os_name, agent_version, utcnow_iso(), capabilities, workspace_root, utcnow_iso()),
    )
    device_id = cur.lastrowid
    record_audit(
        conn,
        actor="system",
        actor_role="SYSTEM",
        user_id=user_id,
        device_id=device_id,
        action="device_registered",
        resource=f"device:{device_id}",
    )
    return {"device_id": device_id, "device_key": device_key}


def get_device(conn, device_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    return dict(row) if row else None


def get_device_by_key_hash(conn, key_hash: str) -> dict | None:
    row = conn.execute("SELECT * FROM devices WHERE device_key_hash = ?", (key_hash,)).fetchone()
    return dict(row) if row else None


def heartbeat(conn, device_key: str) -> dict | None:
    key_hash = _hash_device_key(device_key)
    device = get_device_by_key_hash(conn, key_hash)
    if not device:
        return None
    conn.execute(
        "UPDATE devices SET status = 'ONLINE', last_heartbeat_at = ? WHERE id = ?",
        (utcnow_iso(), device["id"]),
    )
    return get_device(conn, device["id"])


def mark_stale_devices_offline(conn) -> int:
    """Mark devices offline when heartbeat is older than grace period."""
    from datetime import datetime, timedelta, timezone

    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=HEARTBEAT_GRACE_SECONDS)).isoformat()
    cur = conn.execute(
        "UPDATE devices SET status = 'OFFLINE' WHERE status = 'ONLINE' AND last_heartbeat_at < ?",
        (cutoff,),
    )
    return cur.rowcount


def list_devices(conn, *, user_id: int | None = None) -> list[dict]:
    if user_id is not None:
        rows = conn.execute("SELECT * FROM devices WHERE user_id = ? ORDER BY id DESC", (user_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM devices ORDER BY id DESC").fetchall()
    return [dict(row) for row in rows]


def get_device_by_name_for_user(conn, user_id: int, device_name: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM devices WHERE user_id = ? AND device_name = ?", (user_id, device_name)
    ).fetchone()
    return dict(row) if row else None


def device_status_view(conn, row) -> dict:
    """Return product-facing device health plus its active task."""
    data = dict(row)
    try:
        data["capabilities"] = json.loads(data.get("capabilities") or "[]")
    except (TypeError, json.JSONDecodeError):
        data["capabilities"] = []
    heartbeat = data.get("last_heartbeat_at")
    age = None
    if heartbeat:
        try:
            age = max(0, int((datetime.now(timezone.utc) - datetime.fromisoformat(heartbeat)).total_seconds()))
        except ValueError:
            pass
    data["heartbeat_age_seconds"] = age
    if data.get("status") != "ONLINE":
        data["connection_health"] = "OFFLINE"
    elif age is None or age > HEARTBEAT_GRACE_SECONDS // 2:
        data["connection_health"] = "DEGRADED"
    else:
        data["connection_health"] = "HEALTHY"
    task = conn.execute(
        """SELECT id, type, status, progress FROM tasks
           WHERE device_id = ? AND status IN ('PENDING','PLANNING','WAITING_APPROVAL','RUNNING','VERIFYING')
           ORDER BY id DESC LIMIT 1""",
        (data["id"],),
    ).fetchone()
    data["current_task"] = dict(task) if task else None
    return data
