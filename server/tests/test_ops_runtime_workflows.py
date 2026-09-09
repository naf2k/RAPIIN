"""End-to-end Operations Center orchestration and guarded workflows."""
import json
import subprocess
from pathlib import Path

from beresin.database import connect, utcnow_iso
from beresin.ops_incidents import create_proposal, ingest_signal, respond_approval, seed_ops
from beresin.ops_notifications import deliver_pending
from beresin.ops_runtime import dispatch_incident
from beresin.ops_workflows import deploy, provision_worktree, run_coder


def _actor(conn):
    return dict(conn.execute("SELECT * FROM users WHERE role='SUPERVISOR' LIMIT 1").fetchone())


def _incident_and_approval(conn, action_type="CODE_FIX"):
    actor = _actor(conn)
    incident = ingest_signal(conn, source="test", title=f"{action_type} incident", severity="HIGH", summary="Synthetic drill", resource="tests")
    proposal = create_proposal(conn, incident["id"], action_type=action_type, title="Safe action", description="Bounded action", risk="Low", actor=actor)
    respond_approval(conn, proposal["approval_id"], decision="APPROVED", note="Approved for test", actor=actor)
    return incident, proposal


def test_default_agents_exchange_durable_reports():
    conn = connect(); seed_ops(conn)
    incident = ingest_signal(conn, source="runtime", title="Provider failure", severity="HIGH", summary="Provider unavailable")
    results = dispatch_incident(conn, incident["id"], runner=lambda role, prompt: json.dumps({"summary": role, "confidence": 0.9}))
    assert [r["status"] for r in results] == ["COMPLETED"] * 3
    assert conn.execute("SELECT COUNT(*) n FROM ops_agent_assignments WHERE incident_id=?", (incident["id"],)).fetchone()["n"] == 3
    assert conn.execute("SELECT COUNT(*) n FROM ops_agent_messages WHERE incident_id=?", (incident["id"],)).fetchone()["n"] == 3
    conn.close()


def test_telegram_failure_falls_back_to_database(monkeypatch):
    from beresin.config import settings
    monkeypatch.setattr(settings, "ops_telegram_bot_token", "fake")
    monkeypatch.setattr(settings, "ops_telegram_chat_id", "123")
    def fail(*args, **kwargs):
        raise OSError("offline")
    monkeypatch.setattr("urllib.request.urlopen", fail)
    conn = connect(); ingest_signal(conn, source="notify", title="Notify owner", severity="CRITICAL")
    result = deliver_pending(conn)
    assert result[-1]["status"] == "FAILED"
    assert conn.execute("SELECT COUNT(*) n FROM ops_notifications WHERE delivery_status='FAILED'").fetchone()["n"] >= 1
    conn.close()


def test_coder_requires_approval_and_stays_in_worktree(tmp_path, monkeypatch):
    repo = tmp_path / "repo"; repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "ops@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Ops Test"], cwd=repo, check=True)
    (repo / "app.txt").write_text("before\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True); subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True)
    from beresin.config import settings
    monkeypatch.setattr(settings, "ops_worktree_root", str(tmp_path / "worktrees"))
    conn = connect(); incident = ingest_signal(conn, source="code", title="Bug", severity="HIGH")
    try:
        provision_worktree(conn, incident["id"], 999, repo_root=repo)
        assert False, "unapproved worktree must fail"
    except PermissionError:
        pass
    incident, approval = _incident_and_approval(conn)
    change = provision_worktree(conn, incident["id"], approval["approval_id"], repo_root=repo)
    worktree = Path(change["worktree_path"])
    def coder(path, prompt):
        (path / "app.txt").write_text("after\n")
        return "done"
    updated = run_coder(conn, change["id"], runner=coder)
    assert updated["status"] == "READY_FOR_REVIEW"
    assert (repo / "app.txt").read_text() == "before\n"
    assert (worktree / "app.txt").read_text() == "after\n"
    conn.close()


def test_deployment_uses_second_approval_and_rolls_back(monkeypatch):
    conn = connect(); incident, fix = _incident_and_approval(conn)
    now = utcnow_iso()
    change_id = conn.execute("INSERT INTO ops_code_changes(incident_id,approval_id,branch_name,worktree_path,base_commit,commit_sha,status,created_at,updated_at) VALUES(?,?,?,?,?,?,'READY_FOR_REVIEW',?,?)", (incident["id"], fix["approval_id"], "ops/test", "/tmp/test", "base", "artifact123", now, now)).lastrowid
    conn.execute("INSERT INTO ops_check_runs(code_change_id,name,status) VALUES(?,?,'PASSED')", (change_id, "tests"))
    try:
        deploy(conn, incident["id"], change_id, fix["approval_id"], command_runner=lambda action, artifact: True)
        assert False, "code approval must not authorize deployment"
    except PermissionError:
        pass
    actor = _actor(conn)
    proposal = create_proposal(conn, incident["id"], action_type="DEPLOYMENT", title="Deploy", description="Deploy tested artifact", risk="Restart", actor=actor)
    respond_approval(conn, proposal["approval_id"], decision="APPROVED", note="Deploy approved separately", actor=actor)
    def health_failure(*args, **kwargs):
        raise OSError("health down")
    monkeypatch.setattr("urllib.request.urlopen", health_failure)
    actions = []
    result = deploy(conn, incident["id"], change_id, proposal["approval_id"], command_runner=lambda action, artifact: actions.append(action) or True)
    assert result["status"] == "ROLLED_BACK"
    assert actions == ["deploy", "rollback"]
    conn.close()
