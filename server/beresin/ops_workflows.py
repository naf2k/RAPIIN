"""Approved code, CI, deployment and rollback workflows."""
from __future__ import annotations

import hmac
import json
import os
import shlex
import shutil
import subprocess
import urllib.request
from pathlib import Path

from .config import settings
from .database import utcnow_iso
from .ops_incidents import _approval_snapshot, _event, get_incident, operations_frozen

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(command: list[str], cwd: Path, timeout: int = 300, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, check=False, env=env)


def _sandbox_profile(worktree: Path, hermes_command: str) -> str:
    """Permit code reads in the worktree while denying the rest of the user's home."""
    home = Path.home().resolve()
    hermes_binary = Path(hermes_command).resolve()
    hermes_runtime = next((p for p in hermes_binary.parents if p.name == "hermes-agent"), hermes_binary.parent)
    hermes_state = (settings.data_dir / "ops-hermes").resolve()
    git_metadata = (REPO_ROOT / ".git").resolve()
    return (
        '(version 1) (allow default) '
        f'(deny file-read* (subpath "{home}")) '
        f'(allow file-read* (subpath "{worktree}")) '
        f'(allow file-read* (subpath "{git_metadata}")) '
        f'(allow file-read* (subpath "{hermes_runtime}")) '
        f'(allow file-read* (subpath "{hermes_state}")) '
        '(deny file-write*) (allow file-write* (literal "/dev/null")) '
        f'(allow file-write* (subpath "{worktree}")) '
        f'(allow file-write* (subpath "{hermes_state}")) '
        '(allow file-write* (subpath "/tmp")) '
        '(allow file-write* (subpath "/private/tmp"))'
    )


def _approved(conn, approval_id: int, incident_id: int, approval_type: str):
    row = conn.execute("SELECT * FROM ops_approvals WHERE id=? AND incident_id=? AND approval_type=?", (approval_id, incident_id, approval_type)).fetchone()
    if not row or row["status"] != "APPROVED":
        raise PermissionError(f"Approval {approval_type} yang valid diperlukan.")
    now = utcnow_iso()
    if row["expires_at"] and row["expires_at"] <= now:
        conn.execute("UPDATE ops_approvals SET status='EXPIRED' WHERE id=?", (approval_id,))
        raise PermissionError(f"Approval {approval_type} sudah kedaluwarsa.")
    proposal = conn.execute("SELECT * FROM ops_action_proposals WHERE id=?", (row["proposal_id"],)).fetchone()
    expected = _approval_snapshot(incident_id, proposal["id"], proposal["action_type"], proposal["title"], proposal["description"], proposal["risk"] or "")
    if not hmac.compare_digest(row["snapshot_hash"] or "", expected):
        raise PermissionError("Snapshot approval tidak lagi cocok dengan proposal.")
    return row


def provision_worktree(conn, incident_id: int, approval_id: int, repo_root: Path = REPO_ROOT) -> dict:
    if operations_frozen(conn):
        raise PermissionError("Emergency pause aktif.")
    _approved(conn, approval_id, incident_id, "CODE_FIX")
    existing = conn.execute("SELECT * FROM ops_code_changes WHERE incident_id=? AND approval_id=?", (incident_id, approval_id)).fetchone()
    if existing:
        return dict(existing)
    base = _run(["git", "rev-parse", "HEAD"], repo_root)
    if base.returncode:
        raise RuntimeError("Repository Git tidak siap.")
    root = Path(settings.ops_worktree_root) if settings.ops_worktree_root else settings.data_dir / "ops-worktrees"
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve()
    worktree = (root / f"incident-{incident_id}").resolve()
    if root not in worktree.parents:
        raise RuntimeError("Path worktree tidak aman.")
    branch = f"ops/incident-{incident_id}"
    result = _run(["git", "worktree", "add", "-b", branch, str(worktree), base.stdout.strip()], repo_root)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout)[-1000:])
    now = utcnow_iso()
    change_id = conn.execute(
        "INSERT INTO ops_code_changes(incident_id,approval_id,branch_name,worktree_path,base_commit,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
        (incident_id, approval_id, branch, str(worktree), base.stdout.strip(), now, now),
    ).lastrowid
    _event(conn, incident_id, "ISOLATED_WORKTREE_CREATED", "system", "SYSTEM", {"change_id": change_id, "branch": branch, "base_commit": base.stdout.strip()})
    return dict(conn.execute("SELECT * FROM ops_code_changes WHERE id=?", (change_id,)).fetchone())


def run_coder(conn, code_change_id: int, runner=None) -> dict:
    change = conn.execute("SELECT * FROM ops_code_changes WHERE id=?", (code_change_id,)).fetchone()
    if not change:
        raise LookupError("Code change tidak ditemukan.")
    _approved(conn, change["approval_id"], change["incident_id"], "CODE_FIX")
    if operations_frozen(conn):
        raise PermissionError("Emergency pause aktif.")
    worktree = Path(change["worktree_path"]).resolve()
    expected_root = (Path(settings.ops_worktree_root) if settings.ops_worktree_root else settings.data_dir / "ops-worktrees").resolve()
    if expected_root not in worktree.parents or not (worktree / ".git").exists():
        raise PermissionError("Worktree terisolasi tidak valid.")
    incident = get_incident(conn, change["incident_id"])
    prompt = (
        "Perbaiki insiden BERESIN berikut hanya di worktree saat ini. Jangan deploy, jangan mengakses dokumen pengguna, "
        "jangan membaca secret, pertahankan approval boundaries, tambahkan regression test, dan jalankan test terkait. "
        f"Insiden #{incident['id']}: {incident['title']}. Ringkasan: {incident.get('summary') or '-'}"
    )
    conn.execute("UPDATE ops_code_changes SET status='RUNNING',updated_at=? WHERE id=?", (utcnow_iso(), code_change_id)); conn.commit()
    try:
        if runner:
            output = runner(worktree, prompt)
        elif not settings.ops_agents_enabled:
            raise RuntimeError("Runtime Hermes belum diaktifkan.")
        else:
            hermes_command = shutil.which(settings.ops_hermes_command) or str(Path.home() / ".local/bin/hermes")
            if not Path(hermes_command).is_file():
                raise RuntimeError("Hermes CLI tidak ditemukan oleh service account.")
            command = [
                hermes_command, "--cli", "--ignore-user-config", "--ignore-rules",
                "--provider", "custom", "-m", settings.ai_model,
                "-t", "terminal,file", "--in", str(worktree), "-z", prompt,
            ]
            if shutil.which("sandbox-exec"):
                profile = _sandbox_profile(worktree, hermes_command)
                command = ["sandbox-exec", "-p", profile, *command]
            from .ops_runtime import hermes_process_environment
            try:
                completed = _run(command, worktree, timeout=max(settings.ops_agent_timeout_seconds, 300), env=hermes_process_environment("coder"))
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("Coder mencapai batas waktu 300 detik; perubahan parsial dipertahankan untuk review/retry.") from exc
            if completed.returncode:
                raise RuntimeError(f"Coder gagal: {(completed.stderr or completed.stdout)[-1000:]}")
            output = completed.stdout
        diff = _run(["git", "diff", "--stat"], worktree)
        conn.execute("UPDATE ops_code_changes SET status='READY_FOR_REVIEW',diff_summary=?,updated_at=? WHERE id=?", (diff.stdout[:4000], utcnow_iso(), code_change_id))
        _event(conn, change["incident_id"], "CODER_COMPLETED", "Coder", "CODER", {"change_id": code_change_id, "output": output[-2000:], "diff_summary": diff.stdout[:4000]})
    except Exception:
        conn.execute("UPDATE ops_code_changes SET status='FAILED',updated_at=? WHERE id=?", (utcnow_iso(), code_change_id))
        raise
    return dict(conn.execute("SELECT * FROM ops_code_changes WHERE id=?", (code_change_id,)).fetchone())


def run_checks(conn, code_change_id: int) -> list[dict]:
    change = conn.execute("SELECT * FROM ops_code_changes WHERE id=?", (code_change_id,)).fetchone()
    if not change:
        raise LookupError("Code change tidak ditemukan.")
    worktree = Path(change["worktree_path"])
    node_command = shutil.which("node") or str(Path.home() / ".local/bin/node")
    commands = [
        ("backend", [str(REPO_ROOT / "server/.venv/bin/python"), "-m", "pytest", "-q", "server/tests"]),
        ("agent", [str(REPO_ROOT / "agent/.venv/bin/python"), "-m", "pytest", "-q", "agent/tests"]),
        ("javascript-app", [node_command, "--check", "app.js"]),
        ("javascript-chat", [node_command, "--check", "chat.js"]),
        ("javascript-supervisor", [node_command, "--check", "supervisor.js"]),
        ("diff-integrity", ["git", "diff", "--check"]),
    ]
    bandit = REPO_ROOT / "server/.venv/bin/bandit"
    if bandit.is_file():
        commands.append(("security-bandit", [str(bandit), "-q", "-r", "server/beresin", "-lll", "-ii"]))
    conn.execute(
        "UPDATE ops_check_runs SET status='FAILED',output_summary=?,finished_at=? "
        "WHERE code_change_id=? AND status='RUNNING'",
        ("Check terputus sebelum menghasilkan hasil akhir.", utcnow_iso(), code_change_id),
    )
    results = []
    for name, command in commands:
        started = utcnow_iso()
        check_id = conn.execute("INSERT INTO ops_check_runs(code_change_id,name,status,command,started_at) VALUES(?,?,'RUNNING',?,?)", (code_change_id, name, " ".join(command), started)).lastrowid
        conn.commit()
        try:
            completed = _run(command, worktree, timeout=900)
            status = "PASSED" if completed.returncode == 0 else "FAILED"
            summary = ((completed.stdout or "") + "\n" + (completed.stderr or ""))[-8000:]
        except Exception as exc:
            status = "FAILED"
            summary = f"Check tidak dapat dijalankan: {type(exc).__name__}: {exc}"[-8000:]
        conn.execute("UPDATE ops_check_runs SET status=?,output_summary=?,finished_at=? WHERE id=?", (status, summary, utcnow_iso(), check_id))
        results.append({"id": check_id, "name": name, "status": status, "output_summary": summary})
        if status == "FAILED":
            break
    _event(conn, change["incident_id"], "CHECKS_COMPLETED", "system", "SYSTEM", {"change_id": code_change_id, "results": [{"name": r["name"], "status": r["status"]} for r in results]})
    return results


def _latest_checks_passed(conn, code_change_id: int) -> bool:
    rows = conn.execute(
        "SELECT name,status FROM ops_check_runs WHERE code_change_id=? ORDER BY id",
        (code_change_id,),
    ).fetchall()
    latest = {row["name"]: row["status"] for row in rows}
    required = {"backend", "agent", "javascript-app", "javascript-chat", "javascript-supervisor", "diff-integrity"}
    if (REPO_ROOT / "server/.venv/bin/bandit").is_file():
        required.add("security-bandit")
    return all(latest.get(name) == "PASSED" for name in required)


def create_pull_request(conn, code_change_id: int) -> dict:
    change = conn.execute("SELECT * FROM ops_code_changes WHERE id=?", (code_change_id,)).fetchone()
    if not _latest_checks_passed(conn, code_change_id):
        raise PermissionError("Semua check wajib lulus sebelum PR dibuat.")
    worktree = Path(change["worktree_path"])
    _run(["git", "add", "-A"], worktree)
    commit = _run(["git", "commit", "-m", f"fix incident {change['incident_id']}"], worktree)
    if commit.returncode and "nothing to commit" not in (commit.stdout + commit.stderr):
        raise RuntimeError(commit.stderr[-1000:])
    sha = _run(["git", "rev-parse", "HEAD"], worktree).stdout.strip()
    pushed = _run(["git", "push", "-u", "origin", change["branch_name"]], worktree, timeout=180)
    if pushed.returncode:
        raise RuntimeError(pushed.stderr[-1000:])
    pr = _run(["gh", "pr", "create", "--repo", settings.ops_github_repo, "--base", "main", "--head", change["branch_name"], "--title", f"Fix Operations incident #{change['incident_id']}", "--body", f"Generated from approved BERESIN incident #{change['incident_id']}. Deployment still requires separate approval."], worktree, timeout=120)
    if pr.returncode:
        raise RuntimeError(pr.stderr[-1000:])
    url = pr.stdout.strip().splitlines()[-1]
    conn.execute("UPDATE ops_code_changes SET commit_sha=?,pull_request_url=?,updated_at=? WHERE id=?", (sha, url, utcnow_iso(), code_change_id))
    _event(conn, change["incident_id"], "PULL_REQUEST_CREATED", "system", "SYSTEM", {"url": url, "commit": sha})
    return {"commit_sha": sha, "pull_request_url": url}


def deploy(conn, incident_id: int, code_change_id: int, approval_id: int, environment: str = "production", command_runner=None) -> dict:
    if operations_frozen(conn):
        raise PermissionError("Emergency pause aktif.")
    _approved(conn, approval_id, incident_id, "DEPLOYMENT")
    change = conn.execute("SELECT * FROM ops_code_changes WHERE id=? AND incident_id=?", (code_change_id, incident_id)).fetchone()
    if not change or not change["commit_sha"]:
        raise PermissionError("Artifact commit belum tersedia.")
    if not _latest_checks_passed(conn, code_change_id):
        raise PermissionError("Deployment hanya boleh memakai artifact dengan green checks.")
    artifact = change["commit_sha"]
    previous = conn.execute("SELECT artifact_ref FROM ops_deployments WHERE environment=? AND status='SUCCEEDED' ORDER BY id DESC LIMIT 1", (environment,)).fetchone()
    previous_artifact = previous["artifact_ref"] if previous else None
    deploy_id = conn.execute("INSERT INTO ops_deployments(incident_id,code_change_id,approval_id,environment,artifact_ref,previous_artifact_ref,status,created_at,started_at) VALUES(?,?,?,?,?,?,'DEPLOYING',?,?)", (incident_id, code_change_id, approval_id, environment, artifact, previous_artifact, utcnow_iso(), utcnow_iso())).lastrowid
    conn.commit()
    try:
        if command_runner:
            ok = command_runner("deploy", artifact)
        elif settings.ops_deploy_command:
            completed = _run([*shlex.split(settings.ops_deploy_command), artifact], REPO_ROOT, timeout=600); ok = completed.returncode == 0
        else:
            raise RuntimeError("OPS_DEPLOY_COMMAND belum dikonfigurasi.")
        if not ok:
            raise RuntimeError("Perintah deployment gagal.")
        conn.execute("UPDATE ops_deployments SET status='VERIFYING' WHERE id=?", (deploy_id,)); conn.commit()
        with urllib.request.urlopen(settings.ops_health_url, timeout=15) as response:
            health_ok = response.status == 200 and json.loads(response.read()).get("status") in {"ready", "healthy"}
        if not health_ok:
            raise RuntimeError("Post-deploy health check gagal.")
        conn.execute("UPDATE ops_deployments SET status='SUCCEEDED',health_result_json=?,finished_at=? WHERE id=?", (json.dumps({"ok": True}), utcnow_iso(), deploy_id))
        _event(conn, incident_id, "DEPLOYMENT_SUCCEEDED", "system", "SYSTEM", {"deployment_id": deploy_id, "artifact": artifact})
    except Exception as exc:
        rollback_ok = False
        if command_runner:
            rollback_ok = bool(command_runner("rollback", previous_artifact))
        elif settings.ops_rollback_command:
            rollback_ok = _run(shlex.split(settings.ops_rollback_command), REPO_ROOT, timeout=600).returncode == 0
        status = "ROLLED_BACK" if rollback_ok else "FAILED"
        conn.execute("UPDATE ops_deployments SET status=?,health_result_json=?,finished_at=? WHERE id=?", (status, json.dumps({"ok": False, "error": str(exc)[:1000]}), utcnow_iso(), deploy_id))
        _event(conn, incident_id, "DEPLOYMENT_FAILED", "system", "SYSTEM", {"deployment_id": deploy_id, "rollback": rollback_ok, "error": str(exc)[:1000]})
    return dict(conn.execute("SELECT * FROM ops_deployments WHERE id=?", (deploy_id,)).fetchone())
