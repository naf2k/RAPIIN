"""Server-side trash ledger.

The Desktop Agent performs the actual reversible move (see
``agent/rapiin_agent/trash.py``); this module records the batch so the server
can list it to the user and route an undo request back to the same device.

Keeping the ledger on the server means a trash batch stays discoverable even
after a browser reload or a different machine, while the bytes never leave the
user's own computer.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone


def record_trash_entry(
    conn,
    *,
    user_id: int,
    device_id: int | None,
    task_id: int | None,
    trash_id: str | None,
    result: dict,
) -> str | None:
    """Persist a trash batch returned by a device mutation result."""
    if not trash_id:
        return None
    root = result.get("trash_dir")
    items = [
        entry for entry in result.get("summary", [])
        if isinstance(entry, dict)
        and (entry.get("status") == "TRASHED" or entry.get("trashed_to"))
    ]
    conn.execute(
        """
        INSERT INTO trash_entries (id, user_id, device_id, task_id, root, created_at, item_count, manifest_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (id) DO UPDATE SET item_count = excluded.item_count, manifest_json = excluded.manifest_json
        """,
        (
            trash_id,
            user_id,
            device_id,
            task_id,
            root,
            utcnow(),
            len(items),
            json.dumps({"items": items}, ensure_ascii=False),
        ),
    )
    return trash_id


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_trash_entries(conn, *, user_id: int, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM trash_entries WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user_id, max(1, min(limit, 200))),
    ).fetchall()
    return [dict(row) for row in rows]


def get_trash_entry(conn, *, user_id: int, trash_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM trash_entries WHERE id = ? AND user_id = ?", (trash_id, user_id)
    ).fetchone()
    return dict(row) if row else None


def mark_trash_restored(conn, *, user_id: int, trash_id: str) -> None:
    conn.execute(
        "UPDATE trash_entries SET restored_at = ? WHERE id = ? AND user_id = ?",
        (utcnow(), trash_id, user_id),
    )


def undo_window_expired(entry: dict, *, days: int = 30) -> bool:
    """Trash older than the retention window is no longer advertised as undoable."""
    created = entry.get("created_at")
    if not created:
        return False
    try:
        when = datetime.fromisoformat(created)
    except ValueError:
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - when > timedelta(days=days)
