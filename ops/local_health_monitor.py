#!/usr/bin/env python3
"""Monitor a loopback BERESIN deployment and notify on status transitions."""
from __future__ import annotations

import json
import http.client
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "server" / "data" / ".local-health-state"
def current_status() -> tuple[str, str]:
    try:
        connection = http.client.HTTPConnection("127.0.0.1", 8000, timeout=5)
        connection.request("GET", "/ready")
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        if response.status == 200 and payload.get("status") == "ready" and payload.get("database") == "ok":
            return "ready", "Server dan database BERESIN siap."
        return "degraded", "Respons readiness BERESIN tidak valid."
    except Exception as exc:  # noqa: BLE001
        return "down", f"BERESIN tidak dapat dijangkau: {type(exc).__name__}"


def notify(message: str) -> None:
    script = 'display notification "' + message.replace('"', "'") + '" with title "BERESIN Lokal"'
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)


def main() -> int:
    status, message = current_status()
    previous = STATE_PATH.read_text(encoding="utf-8").strip() if STATE_PATH.exists() else ""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(status + "\n", encoding="utf-8")
    if previous and previous != status:
        notify(message)
    print(f"{status}: {message}")
    return 0 if status == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
