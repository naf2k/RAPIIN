"""Tests for approval resume execution and DB migrations."""
import shutil
import sqlite3
import tempfile
from pathlib import Path

from rapiin.database import connect
from rapiin.permissions import sandbox_root


def test_approved_approval_never_falls_back_to_server_filesystem():
    """An approved action without its Desktop Agent must not touch server files."""
    from rapiin.approval import create_approval, respond_approval
    from rapiin.database import db_session
    from rapiin.tasks import create_task, get_task

    root = sandbox_root()
    d = root / ".rapiin_test_approval"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir()
    target = d / "hapus.txt"
    target.write_text("data")

    with db_session() as conn:
        # conftest seeds the supervisor as user id 1.
        user_id = conn.execute("SELECT id FROM users LIMIT 1").fetchone()["id"]
        task_id = create_task(conn, user_id=user_id, device_id=None, type="conversation")
        approval_id = create_approval(
            conn,
            task_id=task_id,
            user_id=user_id,
            requested_by="RAPIIN",
            kind="USER",
            action="Hapus file",
            scope=str(target),
            risk="Permanent",
            tool_name="file_delete",
            tool_args={"path": str(target)},
        )
        assert target.exists()
        respond_approval(
            conn,
            approval_id,
            decision="APPROVED",
            decided_by_id=user_id,
            decided_by_name="User",
            decided_by_role="USER",
        )
        task = get_task(conn, task_id)
        assert task["status"] == "FAILED"
        assert "Desktop Agent" in task["error"]
        assert target.exists()
    shutil.rmtree(d, ignore_errors=True)


def test_rejected_approval_cancels_task():
    """A rejected approval cancels the waiting task without executing."""
    from rapiin.approval import create_approval, respond_approval
    from rapiin.database import db_session
    from rapiin.tasks import create_task, get_task

    with db_session() as conn:
        user_id = conn.execute("SELECT id FROM users LIMIT 1").fetchone()["id"]
        task_id = create_task(conn, user_id=user_id, device_id=None, type="conversation")
        approval_id = create_approval(
            conn,
            task_id=task_id,
            user_id=user_id,
            requested_by="RAPIIN",
            kind="SUPERVISOR",
            action="Bulk delete",
            risk="Permanent",
            tool_name="file_delete",
            tool_args={"path": "/x/y"},
        )
        respond_approval(
            conn,
            approval_id,
            decision="REJECTED",
            decided_by_id=user_id,
            decided_by_name="User",
            decided_by_role="SUPERVISOR",
        )
        task = get_task(conn, task_id)
        assert task["status"] == "CANCELLED"


def test_db_migration_adds_approval_columns():
    """A DB created with the old schema gains tool_name/tool_args columns."""
    path = Path(tempfile.mkdtemp()) / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER, user_id INTEGER, requested_by TEXT, kind TEXT,
            action TEXT, scope TEXT, risk TEXT,
            status TEXT DEFAULT 'PENDING', decided_by INTEGER,
            decided_at TEXT, created_at TEXT
        );
        """
    )
    conn.commit()
    conn.close()

    from rapiin.database import _migrate

    conn = connect(path)
    _migrate(conn)
    conn.commit()
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(approvals)").fetchall()}
    conn.close()
    assert "tool_name" in cols
    assert "tool_args" in cols
