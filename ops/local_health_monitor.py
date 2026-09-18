#!/usr/bin/env python3
"""Monitor a loopback RAPIIN deployment and notify on status transitions."""
from __future__ import annotations

import json
import http.client
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "server" / "data" / ".local-health-state"


def monitoring_token() -> str:
    token = os.environ.get("RAPIIN_MONITORING_TOKEN", "").strip()
    token_file = os.environ.get("RAPIIN_MONITORING_TOKEN_FILE", "").strip()
    # launchd does not inherit the interactive shell environment. Read only
    # the two monitoring settings from the server's protected local env file.
    env_path = ROOT / "server" / ".env"
    if not token and env_path.exists():
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                key, separator, value = line.partition("=")
                if not separator or key.strip() not in {"RAPIIN_MONITORING_TOKEN", "RAPIIN_MONITORING_TOKEN_FILE"}:
                    continue
                clean = value.strip().strip('"').strip("'")
                if key.strip() == "RAPIIN_MONITORING_TOKEN":
                    token = clean
                elif not token_file:
                    token_file = clean
        except OSError:
            pass
    if not token and token_file:
        try:
            token_path = Path(token_file)
            if not token_path.is_absolute():
                token_path = ROOT / "server" / token_path
            token = token_path.read_text(encoding="utf-8").strip()
        except OSError:
            pass
    return token


def send_signal(title: str, severity: str, summary: str, resource: str, details: dict | None = None) -> bool:
    """Best-effort handoff to the server incident engine."""
    token = monitoring_token()
    if not token:
        return False
    body = json.dumps({
        "source": "local-health-monitor", "title": title, "severity": severity,
        "summary": summary, "resource": resource, "details": details or {},
    })
    try:
        connection = http.client.HTTPConnection("127.0.0.1", 8000, timeout=5)
        connection.request("POST", "/api/internal/ops/signals", body=body, headers={
            "Authorization": f"Bearer {token}", "Content-Type": "application/json",
        })
        response = connection.getresponse()
        response.read()
        connection.close()
        return response.status < 300
    except OSError:
        return False


def infrastructure_checks() -> list[tuple[str, str, str, str, dict]]:
    findings = []
    usage = shutil.disk_usage(ROOT)
    free_percent = round((usage.free / usage.total) * 100, 1)
    if free_percent < 10:
        findings.append(("Disk space critically low", "CRITICAL", f"Ruang disk tersisa {free_percent}%.", str(ROOT), {"free_percent": free_percent}))
    backup_dir = Path.home() / "RapiinBackups"
    backups = [p for p in backup_dir.glob("*") if p.is_file()] if backup_dir.exists() else []
    if not backups:
        findings.append(("Backup verification missing", "HIGH", "Belum ada artefak backup lokal yang dapat diverifikasi.", str(backup_dir), {}))
    else:
        newest = max(backups, key=lambda p: p.stat().st_mtime)
        age_hours = (datetime.now(timezone.utc).timestamp() - newest.stat().st_mtime) / 3600
        if age_hours > 48:
            findings.append(("Backup is stale", "HIGH", f"Backup terbaru berusia {age_hours:.1f} jam.", str(newest), {"age_hours": round(age_hours, 1)}))
    token = monitoring_token()
    if token:
        try:
            connection = http.client.HTTPConnection("127.0.0.1", 8000, timeout=5)
            connection.request("GET", "/api/internal/ops/health", headers={"Authorization": f"Bearer {token}"})
            response = connection.getresponse()
            payload = json.loads(response.read())
            connection.close()
            if response.status != 200 or payload.get("status") != "healthy":
                findings.append(("Operations monitor heartbeat stale", "CRITICAL", "Operations loop atau queue worker tidak mengirim heartbeat tepat waktu.", "operations-runtime", payload))
        except Exception as exc:
            findings.append(("Operations meta-monitor unavailable", "CRITICAL", f"Health Operations tidak dapat dibaca: {type(exc).__name__}.", "operations-runtime", {}))
    return findings
def current_status() -> tuple[str, str]:
    try:
        connection = http.client.HTTPConnection("127.0.0.1", 8000, timeout=5)
        connection.request("GET", "/ready")
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        if response.status == 200 and payload.get("status") == "ready" and payload.get("database") == "ok":
            return "ready", "Server dan database RAPIIN siap."
        return "degraded", "Respons readiness RAPIIN tidak valid."
    except Exception as exc:  # noqa: BLE001
        return "down", f"RAPIIN tidak dapat dijangkau: {type(exc).__name__}"


def notify(message: str) -> None:
    script = 'display notification "' + message.replace('"', "'") + '" with title "RAPIIN Lokal"'
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)


def main() -> int:
    status, message = current_status()
    previous = STATE_PATH.read_text(encoding="utf-8").strip() if STATE_PATH.exists() else ""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(status + "\n", encoding="utf-8")
    if previous and previous != status:
        notify(message)
    if status == "ready":
        for title, severity, summary, resource, details in infrastructure_checks():
            send_signal(title, severity, summary, resource, details)
    print(f"{status}: {message}")
    return 0 if status == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
