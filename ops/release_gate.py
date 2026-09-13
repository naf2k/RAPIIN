#!/usr/bin/env python3
"""Run reproducible local release gates and print a machine-readable report."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKS = {
    "backend_tests": ([str(ROOT / "server/.venv/bin/python"), "-m", "pytest", "-q"], ROOT / "server"),
    "agent_tests": ([str(ROOT / "agent/.venv/bin/python"), "-m", "pytest", "-q"], ROOT / "agent"),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, help="optional JSON output path")
    parser.add_argument("--topology", choices=["public", "local-macos"], default="public")
    args = parser.parse_args()
    external_gates = {
        "macos_windows_reboot": "requires physical/VM reboot evidence",
        "terminal_agent_os_matrix": "requires clean macOS and Windows hosts, including real reboot evidence",
        "tls_alerting_restore_rollback": "requires staging infrastructure",
        "penetration_test": "requires approved staging target and tester",
    } if args.topology == "public" else {}
    checks = dict(CHECKS)
    if args.topology == "local-macos":
        checks["macos_reboot_probe"] = (["beresin", "startup-probe", "verify"], ROOT)
        checks["local_credentialed_uat"] = (
            [str(ROOT / "server/.venv/bin/python"), str(ROOT / "ops/local_uat.py")],
            ROOT,
        )
        checks["local_health"] = (["python3", str(ROOT / "ops/local_health_monitor.py")], ROOT)
    report = {
        "generated_at_epoch": int(time.time()),
        "topology": args.topology,
        "checks": {},
        "external_gates": external_gates,
    }
    failed = False
    for name, (command, cwd) in checks.items():
        if not shutil.which(command[0]) and not Path(command[0]).exists():
            report["checks"][name] = {"status": "BLOCKED", "reason": f"missing command: {command[0]}"}
            failed = True
            continue
        environment = os.environ.copy()
        if name == "backend_tests":
            environment.update({
                "BERESIN_ENV": "test",
                "BERESIN_INIT_SUPERVISOR_EMAIL": "supervisor@beresin.example.com",
                "BERESIN_INIT_SUPERVISOR_PASSWORD": "Supervisor123!",
                "BERESIN_INIT_SUPERVISOR_PASSWORD_FILE": "",
                "BERESIN_SECRET_KEY_FILE": "",
                "BERESIN_MONITORING_TOKEN_FILE": "",
                "BERESIN_ALLOW_PUBLIC_REGISTRATION": "true",
            })
        elif name == "agent_tests":
            # Agent tests must never read or clear the operator's real ~/.beresin.
            environment["HOME"] = tempfile.mkdtemp(prefix="beresin-agent-test-home-")
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=180,
            env=environment,
        )
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
