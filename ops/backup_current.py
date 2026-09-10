#!/usr/bin/env python3
"""Back up whichever database backend BERESIN currently uses."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from beresin.config import settings

backup_dir = Path.home() / "BeresinBackups"
if settings.beresin_database_url:
    command = [sys.executable, str(ROOT / "ops" / "backup_postgres.py"), str(backup_dir), "--database-url", settings.beresin_database_url]
else:
    command = [sys.executable, str(ROOT / "ops" / "backup_sqlite.py"), str(settings.db_path), str(backup_dir)]
raise SystemExit(subprocess.run(command, check=False).returncode)
