#!/usr/bin/env python3
"""Validate a backup and restore it only to a non-existing destination."""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("backup", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    backup = args.backup.resolve(strict=True)
    destination = args.destination.resolve()
    if destination.exists():
        raise SystemExit("destination already exists; refusing to overwrite")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(f"file:{backup}?mode=ro", uri=True) as src:
        if src.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise SystemExit("backup failed integrity_check")
        tables = {row[0] for row in src.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        required = {"users", "devices", "tasks", "audit_log"}
        if not required.issubset(tables):
            raise SystemExit(
                "backup is not a RAPIIN database; missing tables: "
                + ", ".join(sorted(required - tables))
            )
        with sqlite3.connect(destination) as dst:
            src.backup(dst)
    destination.chmod(0o600)
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
