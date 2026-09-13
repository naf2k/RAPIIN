#!/usr/bin/env python3
"""Wall-clock soak monitor for local AI Operations; performs no mutations."""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from beresin.audit import verify_audit_chain
from beresin.config import settings
from beresin.database import connect

READY_URL = "http://127.0.0.1:8000/ready"


def wait_for_readiness(timeout_seconds: int = 300) -> bool:
    """Wait until the server answers before the first sample is counted.

    The soak LaunchAgent shares RunAtLoad with the server, so after a reboot it
    can start sampling while the API is still booting and record failures that
    say nothing about stability. Bounded so a genuinely dead server is still
    reported.
    """
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(READY_URL, timeout=5) as response:
                if response.status == 200:
                    return True
        except Exception:  # noqa: BLE001 - retry until the bounded deadline
            pass
        time.sleep(5)
    return False


def sample() -> dict:
    with urllib.request.urlopen(READY_URL, timeout=5) as response:
        ready = json.loads(response.read().decode())
    conn = connect()
    try:
        integrity = verify_audit_chain(conn)
        duplicates = conn.execute(("""SELECT COUNT(*) n FROM (
            SELECT fingerprint FROM ops_incidents
            WHERE status NOT IN ('RESOLVED','REJECTED') GROUP BY fingerprint HAVING COUNT(*) > 1
        ) duplicated""")).fetchone()["n"]
        active = conn.execute("SELECT COUNT(*) n FROM ops_agent_assignments WHERE status='ACTIVE'").fetchone()["n"]
    finally:
        conn.close()
    return {
        "ready": ready.get("status") == "ready" and ready.get("database") == "ok",
        "queue": ready.get("queue"), "audit_valid": integrity.get("valid") is True,
        "duplicate_active_incidents": duplicates, "active_assignments": active,
    }


def build_report(started, finished, args, samples: int, gaps: int, failures: list, status: str, startup_ready: bool = True) -> dict:
    return {
        "status": status,
        "started_at": started.isoformat(), "finished_at": finished.isoformat(),
        "duration_hours": args.duration_hours,
        "wall_clock_hours": round((finished - started).total_seconds() / 3600, 2),
        "samples": samples, "gaps": gaps, "failures": failures,
        "startup_ready": startup_ready,
        "passed": not failures,
    }


def write_report(output: Path, report: dict) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration-hours", type=float, default=24)
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument("--output", type=Path, default=ROOT / "server/data/ai-ops-soak.json")
    args = parser.parse_args()
    settings.validate_for_startup()
    # Do not start the clock until the API answers: after a reboot this job and
    # the server start together, and sampling too early records failures that
    # describe the boot, not the run.
    startup_ready = wait_for_readiness()
    started = datetime.now(timezone.utc)
    # Wall-clock deadline: host sleep must consume the budget, not pause it,
    # otherwise a suspended laptop silently stretches the soak.
    deadline = time.time() + args.duration_hours * 3600
    failures, samples, gaps = [], 0, 0
    previous_wall: datetime | None = None
    while time.time() < deadline:
        now_wall = datetime.now(timezone.utc)
        if previous_wall is not None:
            elapsed = (now_wall - previous_wall).total_seconds()
            if elapsed > args.interval_seconds * 3 + 5:
                # A suspended host cannot observe readiness; record the blind
                # spot instead of reporting a green 24h run.
                gaps += 1
                failures.append({
                    "at": now_wall.isoformat(), "error": "SamplingGap", "gap_seconds": round(elapsed, 1),
                })
        previous_wall = now_wall
        samples += 1
        try:
            item = sample()
            if not item["ready"] or not item["audit_valid"] or item["duplicate_active_incidents"]:
                failures.append({"at": datetime.now(timezone.utc).isoformat(), "sample": item})
        except Exception as exc:
            failures.append({"at": datetime.now(timezone.utc).isoformat(), "error": type(exc).__name__})
        # Rewrite the report every sample so an operator can read progress
        # instead of waiting for the run to finish.
        write_report(args.output, build_report(started, datetime.now(timezone.utc), args, samples, gaps, failures, "running", startup_ready))
        time.sleep(min(args.interval_seconds, max(0, deadline - time.time())))
    finished = datetime.now(timezone.utc)
    report = build_report(started, finished, args, samples, gaps, failures, "completed", startup_ready)
    write_report(args.output, report)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
