#!/usr/bin/env python3
"""Run an accelerated, non-production Operations Center incident drill."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    commands = [
        [str(ROOT / "server/.venv/bin/python"), "-m", "pytest", "-q", "server/tests/test_operations_center.py", "server/tests/test_ops_runtime_workflows.py", "server/tests/test_ops_adapter.py", "server/tests/test_ops_safety.py", "server/tests/test_ops_maintenance.py"],
        [str(ROOT / "agent/.venv/bin/python"), "-m", "pytest", "-q", "agent/tests"],
    ]
    checks = []
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        checks.append({"command": " ".join(command), "passed": result.returncode == 0, "summary": ((result.stdout or "") + (result.stderr or ""))[-1200:]})
    report = {
        "drill": "accelerated-incident-response",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "production_mutation": False,
        "scenarios": [
            "signal deduplication and audit timeline",
            "Lead Security Diagnostic durable coordination",
            "role-scoped Operations tool gateway",
            "prompt injection and recursive secret redaction",
            "assignment lease recovery and bounded retry",
            "Lead final synthesis and read-only proposal",
            "daily digest grouping and notification backoff",
            "approval expiry idempotency and snapshot integrity",
            "audit hash-chain tamper detection",
            "retention minimization while preserving evidence hashes",
            "provider circuit breaker and approval reminder idempotency",
            "Telegram failure database fallback",
            "unapproved Coder rejection",
            "isolated worktree source protection",
            "separate deployment approval",
            "failed health check rollback",
            "emergency pause blocks desktop agent",
        ],
        "checks": checks,
        "passed": all(item["passed"] for item in checks),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
