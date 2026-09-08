"""Isolated per-user memory and conversation context storage."""
from .database import utcnow_iso


def set_memory(conn, user_id: int, kind: str, key: str, value: str) -> None:
    now = utcnow_iso()
    conn.execute(
        """
        INSERT INTO memory (user_id, kind, key, value, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (user_id, kind, key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (user_id, kind, key, value, now),
    )


def get_memory(conn, user_id: int, kind: str = "private") -> dict[str, str]:
    rows = conn.execute(
        "SELECT key, value FROM memory WHERE user_id = ? AND kind = ?", (user_id, kind)
    ).fetchall()
    return {row["key"]: row["value"] for row in rows}


def list_memory(conn, user_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT kind, key, value, updated_at FROM memory WHERE user_id = ? ORDER BY updated_at DESC",
        (user_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def clear_memory(conn, user_id: int) -> None:
    conn.execute("DELETE FROM memory WHERE user_id = ?", (user_id,))


def get_conversation_messages(conn, conversation_id: int, limit: int = 40) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, role, content, tool_name, created_at FROM messages
        WHERE conversation_id = ?
        ORDER BY id ASC
        LIMIT ?
        """,
        (conversation_id, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def add_message(conn, conversation_id: int, role: str, content: str, tool_name: str | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO messages (conversation_id, role, content, tool_name, created_at) VALUES (?, ?, ?, ?, ?)",
        (conversation_id, role, content, tool_name, utcnow_iso()),
    )
    conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (utcnow_iso(), conversation_id))
    return cur.lastrowid
