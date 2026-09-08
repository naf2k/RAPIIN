#!/usr/bin/env python3
"""Create a consistent SQLite backup without copying a live WAL database."""
from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("backup_dir", type=Path)
    args = parser.parse_args()
    source = args.database.resolve(strict=True)
    args.backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = (args.backup_dir / f"beresin-{stamp}.db").resolve()
    try:
        # WAL databases need a normal connection so SQLite can coordinate the
        # shared-memory file while taking a transactionally consistent backup.
        with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
            src.backup(dst)
            result = dst.execute("PRAGMA integrity_check").fetchone()[0]
            tables = {row[0] for row in dst.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            required = {"users", "devices", "tasks", "audit_log"}
            if result != "ok" or not required.issubset(tables):
                raise RuntimeError(
                    f"backup validation failed: integrity={result}, "
                    f"missing_tables={sorted(required - tables)}"
                )
    except Exception:
        target.unlink(missing_ok=True)
        raise
    target.chmod(0o600)
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
