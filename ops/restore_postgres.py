#!/usr/bin/env python3
"""Restore a verified RAPIIN dump only into an empty PostgreSQL target."""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("backup", type=Path)
    parser.add_argument("--database-url", default=os.getenv("RAPIIN_DATABASE_URL", ""))
    parser.add_argument("--confirm-empty-target", action="store_true")
    args = parser.parse_args()
    backup = args.backup.resolve(strict=True)
    if not args.confirm_empty_target:
        raise SystemExit("Tambahkan --confirm-empty-target setelah memastikan target kosong.")
    sidecar = backup.with_suffix(backup.suffix + ".sha256")
    expected = sidecar.read_text(encoding="utf-8").split()[0] if sidecar.is_file() else ""
    actual = hashlib.sha256(backup.read_bytes()).hexdigest()
    if not expected or expected != actual:
        raise SystemExit("Checksum backup PostgreSQL tidak valid.")
    import psycopg
    with psycopg.connect(args.database_url) as conn:
        count = conn.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'").fetchone()[0]
        if count:
            raise SystemExit("Target restore tidak kosong.")
    pg_restore = shutil.which("pg_restore") or next((str(path) for path in (Path("/usr/local/bin/pg_restore"), Path("/opt/homebrew/bin/pg_restore")) if path.is_file()), "")
    if not pg_restore:
        raise SystemExit("pg_restore tidak ditemukan.")
    check = subprocess.run([pg_restore, "--list", str(backup)], capture_output=True, text=True)
    if check.returncode or "TABLE public users" not in check.stdout:
        raise SystemExit("Archive bukan backup RAPIIN yang valid.")
    restored = subprocess.run([pg_restore, "--no-owner", "--no-acl", "--dbname", args.database_url, str(backup)], capture_output=True, text=True)
    if restored.returncode:
        raise SystemExit("pg_restore gagal: " + (restored.stderr or "unknown error")[-500:])
    with psycopg.connect(args.database_url) as conn:
        users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        incidents = conn.execute("SELECT COUNT(*) FROM ops_incidents").fetchone()[0]
    print({"checksum": actual, "users": users, "ops_incidents": incidents})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
