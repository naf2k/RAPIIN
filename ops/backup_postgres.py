#!/usr/bin/env python3
"""Create a restricted PostgreSQL custom-format backup plus SHA-256 sidecar."""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("backup_dir", type=Path)
    parser.add_argument("--database-url", default=os.getenv("RAPIIN_DATABASE_URL", ""))
    args = parser.parse_args()
    if not args.database_url.startswith(("postgresql://", "postgres://")):
        raise SystemExit("RAPIIN_DATABASE_URL PostgreSQL wajib dikonfigurasi.")
    args.backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = args.backup_dir / f"rapiin-postgres-{stamp}.dump"
    pg_dump = shutil.which("pg_dump") or next((str(path) for path in (Path("/usr/local/bin/pg_dump"), Path("/opt/homebrew/bin/pg_dump")) if path.is_file()), "")
    if not pg_dump:
        raise SystemExit("pg_dump tidak ditemukan.")
    result = subprocess.run([pg_dump, "--format=custom", "--no-owner", "--no-acl", "--file", str(target), args.database_url], capture_output=True, text=True)
    if result.returncode:
        target.unlink(missing_ok=True)
        raise SystemExit("pg_dump gagal: " + (result.stderr or "unknown error")[-500:])
    target.chmod(0o600)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    sidecar = target.with_suffix(target.suffix + ".sha256")
    sidecar.write_text(f"{digest}  {target.name}\n", encoding="utf-8")
    sidecar.chmod(0o600)
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
