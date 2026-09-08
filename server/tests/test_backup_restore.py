import sqlite3
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_backup_and_restore_drill(tmp_path):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        for table in ("users", "devices", "tasks", "audit_log"):
            conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO users DEFAULT VALUES")

    backup_dir = tmp_path / "backups"
    backup = subprocess.run(
        [sys.executable, str(ROOT / "ops/backup_sqlite.py"), str(source), str(backup_dir)],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    restored = tmp_path / "restored.db"
    subprocess.run(
        [sys.executable, str(ROOT / "ops/restore_sqlite.py"), backup, str(restored)],
        check=True,
    )
    with sqlite3.connect(restored) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 1


def test_restore_rejects_empty_sqlite_file(tmp_path):
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    result = subprocess.run(
        [sys.executable, str(ROOT / "ops/restore_sqlite.py"), str(empty), str(tmp_path / "bad.db")],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "not a BERESIN database" in result.stderr
