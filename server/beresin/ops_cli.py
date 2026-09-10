"""Operator CLI for local AI Operations readiness."""
from __future__ import annotations

import argparse
import http.client
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .audit import verify_audit_chain
from .config import settings
from .database import connect
from .ops_notifications import telegram_configured
from .ops_runtime import provider_circuit_open
from .queue_backend import redis_ready


def readiness() -> dict:
    settings.validate_for_startup()
    checks: dict[str, dict] = {}

    def record(name: str, ok: bool, detail: str) -> None:
        checks[name] = {"ok": bool(ok), "detail": detail}

    try:
        connection = http.client.HTTPConnection("127.0.0.1", 8000, timeout=5)
        connection.request("GET", "/ready")
        response = connection.getresponse()
        payload = json.loads(response.read().decode())
        connection.close()
        record("server", response.status == 200 and payload.get("status") == "ready", payload.get("status", "invalid"))
    except Exception as exc:
        record("server", False, type(exc).__name__)

    try:
        conn = connect()
        conn.execute("SELECT 1").fetchone()
        roles = {row["role"] for row in conn.execute("SELECT role FROM ops_agents").fetchall()}
        record("database", True, "postgresql" if settings.beresin_database_url else "sqlite")
        record("roles", roles == {"LEAD", "SECURITY", "DIAGNOSTIC", "CODER"}, ",".join(sorted(roles)))
        integrity = verify_audit_chain(conn)
        record("audit_chain", integrity.get("valid") is True, f"events={integrity.get('count', 0)}")
        record("provider_circuit", not provider_circuit_open(conn), "closed" if not provider_circuit_open(conn) else "open")
        pending = conn.execute("SELECT COUNT(*) n FROM ops_agent_assignments WHERE status IN ('PENDING','ACTIVE')").fetchone()["n"]
        stale = conn.execute(
            "SELECT COUNT(*) n FROM ops_agent_assignments WHERE "
            "(status='ACTIVE' AND lease_expires_at IS NOT NULL AND lease_expires_at < ?) OR "
            "(status='PENDING' AND created_at < ?)",
            (
                datetime.now(timezone.utc).isoformat(),
                datetime.fromtimestamp(
                    datetime.now(timezone.utc).timestamp() - settings.ops_agent_timeout_seconds * 2,
                    timezone.utc,
                ).isoformat(),
            ),
        ).fetchone()["n"]
        record("assignment_queue", stale == 0, f"in_flight={pending},stale={stale}")
        conn.close()
    except Exception as exc:
        record("database", False, type(exc).__name__)

    record("redis", redis_ready(), "configured" if settings.beresin_redis_url else "inline")
    hermes = shutil.which(settings.ops_hermes_command) or str(Path.home() / ".local/bin/hermes")
    record("hermes", Path(hermes).is_file() and bool(settings.ops_hermes_commit), settings.ops_hermes_version)
    record("operations_enabled", settings.ops_agents_enabled, "enabled" if settings.ops_agents_enabled else "disabled")
    record("telegram", telegram_configured(), "configured" if telegram_configured() else "not configured")

    if shutil.which("launchctl"):
        result = subprocess.run(["launchctl", "list"], capture_output=True, text=True, check=False)
        labels = {"com.beresin.server", "com.beresin.agent", "com.beresin.monitor", "com.beresin.backup"}
        if settings.beresin_redis_url:
            labels.add("com.beresin.worker")
        missing = sorted(label for label in labels if label not in result.stdout)
        record("services", not missing, "all loaded" if not missing else "missing=" + ",".join(missing))

    backups = list((Path.home() / "BeresinBackups").glob("*"))
    fresh = [item for item in backups if item.is_file() and datetime.now(timezone.utc).timestamp() - item.stat().st_mtime < 172800]
    record("backup", bool(fresh), f"fresh={len(fresh)}")
    return {"ready": all(item["ok"] for item in checks.values()), "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(prog="beresin-ops")
    parser.add_argument("command", choices=["verify"])
    args = parser.parse_args()
    report = readiness()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ready"] else 1
