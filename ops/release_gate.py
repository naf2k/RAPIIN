#!/usr/bin/env python3
"""Run reproducible local release gates and print a machine-readable report."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKS = {
    "backend_tests": ([str(ROOT / "server/.venv/bin/python"), "-m", "pytest", "-q"], ROOT / "server"),
    "agent_tests": ([str(ROOT / "agent/.venv/bin/python"), "-m", "pytest", "-q"], ROOT / "agent"),
    "frontend_syntax": (["node", "--check", "chat.js"], ROOT),
    "ui_accessibility": (["npm", "run", "test:ui"], ROOT),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, help="optional JSON output path")
    args = parser.parse_args()
    report = {"generated_at_epoch": int(time.time()), "checks": {}, "external_gates": {
        "docker_image_scan": "PASS only in CI or a host with Docker",
        "macos_windows_reboot": "requires physical/VM reboot evidence",
        "terminal_agent_os_matrix": "requires clean macOS and Windows hosts, including real reboot evidence",
        "live_provider": "requires production provider credential",
        "tls_alerting_restore_rollback": "requires staging infrastructure",
        "penetration_test": "requires approved staging target and tester",
    }}
    failed = False
    for name, (command, cwd) in CHECKS.items():
        if not shutil.which(command[0]) and not Path(command[0]).exists():
            report["checks"][name] = {"status": "BLOCKED", "reason": f"missing command: {command[0]}"}
            failed = True
            continue
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=180)
        report["checks"][name] = {
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "exit_code": result.returncode,
            "summary": (result.stdout + result.stderr)[-2000:],
        }
        failed |= result.returncode != 0
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
