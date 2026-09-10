"""End-to-end Operations Center orchestration and guarded workflows."""
import json
import subprocess
from pathlib import Path

from beresin.database import connect, utcnow_iso
from beresin.ops_incidents import create_proposal, ingest_signal, respond_approval, seed_ops
from beresin.ops_notifications import deliver_pending
from beresin.ops_runtime import _daily_budget_available, dispatch_incident, read_usage_report, recover_expired_assignments
from beresin.ops_workflows import REPO_ROOT, _latest_checks_passed, _sandbox_profile, cancel_code_change, cleanup_code_worktree, deploy, provision_worktree, run_checks, run_coder


def test_read_usage_report_supports_official_hermes_fields(tmp_path):
    path = tmp_path / "usage.json"
    path.write_text('{"input_tokens": 120, "output_tokens": 30, "api_calls": 2, "estimated_cost_usd": 0.0125}')
    assert read_usage_report(path) == {"input_tokens": 120, "output_tokens": 30, "api_calls": 2, "estimated_cost_usd": 0.0125}


def test_read_usage_report_is_safe_for_invalid_file(tmp_path):
    path = tmp_path / "usage.json"
    path.write_text("not-json")
    assert read_usage_report(path) == {"input_tokens": 0, "output_tokens": 0, "api_calls": 0, "estimated_cost_usd": 0.0}


def test_daily_budget_fails_closed_at_estimated_cost_limit(monkeypatch):
    conn = connect(); seed_ops(conn)
    agent = conn.execute("SELECT id FROM ops_agents LIMIT 1").fetchone()
    conn.execute(
        "INSERT INTO ops_agent_usage(agent_id,estimated_cost_usd,status,created_at) VALUES(?,?,'SUCCEEDED',?)",
        (agent["id"], 2.0, utcnow_iso()),
    )
    monkeypatch.setattr("beresin.ops_runtime.settings.ops_agent_daily_run_limit", 100)
    monkeypatch.setattr("beresin.ops_runtime.settings.ops_agent_daily_cost_limit_usd", 2.0)
    assert not _daily_budget_available(conn)
    conn.close()


def test_monthly_budget_fails_closed(monkeypatch):
    conn = connect(); seed_ops(conn)
    agent = conn.execute("SELECT id FROM ops_agents LIMIT 1").fetchone()
    conn.execute(
        "INSERT INTO ops_agent_usage(agent_id,estimated_cost_usd,status,created_at) VALUES(?,?,'SUCCEEDED',?)",
        (agent["id"], 101.0, utcnow_iso()),
    )
    monkeypatch.setattr("beresin.ops_runtime.settings.ops_agent_daily_run_limit", 100)
    monkeypatch.setattr("beresin.ops_runtime.settings.ops_agent_daily_cost_limit_usd", 200.0)
    monkeypatch.setattr("beresin.ops_runtime.settings.ops_agent_monthly_cost_limit_usd", 100.0)
    assert not _daily_budget_available(conn)
    conn.close()


def _actor(conn):
    return dict(conn.execute("SELECT * FROM users WHERE role='SUPERVISOR' LIMIT 1").fetchone())


def test_operations_repo_root_points_to_checkout():
    assert (REPO_ROOT / ".git").exists()
    assert (REPO_ROOT / "server" / "beresin").is_dir()


def test_coder_sandbox_denies_home_reads_except_assigned_scopes(tmp_path):
    worktree = tmp_path / "worktree"
    profile = _sandbox_profile(worktree, "/usr/bin/true")
    assert f'(deny file-read* (subpath "{(Path.home() / "Documents").resolve()}"))' in profile
    assert f'(deny file-read* (subpath "{(REPO_ROOT / "server" / ".env").resolve()}"))' in profile
    assert f'(allow file-read* (subpath "{worktree}"))' in profile
    assert f'(allow file-write* (subpath "{worktree}"))' in profile
    assert f'(allow file-read* (subpath "{(Path.home() / ".hermes" / "hermes-agent").resolve()}"))' in profile


def test_coder_review_marks_new_files_as_intent_to_add(tmp_path, monkeypatch):
    # The exact command is a safety regression: untracked Coder output must be visible in review.
    source = (REPO_ROOT / "server" / "beresin" / "ops_workflows.py").read_text()
    assert '_run(["git", "add", "-N", "."], worktree)' in source


def test_check_runner_records_launch_failure_instead_of_leaving_running(tmp_path, monkeypatch):
    conn = connect(); incident, approval = _incident_and_approval(conn)
    now = utcnow_iso()
    change_id = conn.execute(
        "INSERT INTO ops_code_changes(incident_id,approval_id,branch_name,worktree_path,base_commit,status,created_at,updated_at) "
        "VALUES(?,?,?,?,?,'READY_FOR_REVIEW',?,?)",
        (incident["id"], approval["approval_id"], "ops/test-check", str(tmp_path), "base", now, now),
    ).lastrowid
    monkeypatch.setattr("beresin.ops_workflows._run", lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError("missing")))
    results = run_checks(conn, change_id)
    assert results[0]["status"] == "FAILED"
    row = conn.execute("SELECT status,finished_at FROM ops_check_runs WHERE code_change_id=?", (change_id,)).fetchone()
    assert row["status"] == "FAILED"
    assert row["finished_at"]
    conn.close()


def test_latest_successful_rerun_supersedes_old_failure():
    conn = connect(); incident, approval = _incident_and_approval(conn)
    now = utcnow_iso()
    change_id = conn.execute(
        "INSERT INTO ops_code_changes(incident_id,approval_id,branch_name,worktree_path,base_commit,status,created_at,updated_at) "
        "VALUES(?,?,?,?,?,'READY_FOR_REVIEW',?,?)",
        (incident["id"], approval["approval_id"], "ops/test-rerun", "/tmp/test-rerun", "base", now, now),
    ).lastrowid
    conn.execute("INSERT INTO ops_check_runs(code_change_id,name,status) VALUES(?,?,'FAILED')", (change_id, "javascript"))
    for name in ("backend", "agent", "javascript-app", "javascript-chat", "javascript-supervisor", "diff-integrity", "security-bandit"):
        conn.execute("INSERT INTO ops_check_runs(code_change_id,name,status) VALUES(?,?,'PASSED')", (change_id, name))
    assert _latest_checks_passed(conn, change_id)
    conn.close()


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
    assert [r["status"] for r in results] == ["COMPLETED"] * 4
    assert conn.execute("SELECT COUNT(*) n FROM ops_agent_assignments WHERE incident_id=?", (incident["id"],)).fetchone()["n"] == 4
    assert conn.execute("SELECT COUNT(*) n FROM ops_agent_messages WHERE incident_id=?", (incident["id"],)).fetchone()["n"] == 4
    assert conn.execute("SELECT status FROM ops_incidents WHERE id=?", (incident["id"],)).fetchone()["status"] == "INVESTIGATING"
    proposal = conn.execute("SELECT action_type,proposed_by_agent_id FROM ops_action_proposals WHERE incident_id=?", (incident["id"],)).fetchone()
    assert proposal["action_type"] == "INVESTIGATION" and proposal["proposed_by_agent_id"]
    conn.close()


def test_later_agents_receive_prior_structured_reports():
    conn = connect(); seed_ops(conn)
    incident = ingest_signal(conn, source="runtime", title="Coordinated incident", severity="HIGH")
    prompts = []
    def runner(role, prompt):
        prompts.append((role, prompt))
        return json.dumps({"summary": f"{role} report", "confidence": 0.9})
    dispatch_incident(conn, incident["id"], runner=runner)
    assert "LEAD report" in prompts[1][1]
    assert "SECURITY report" in prompts[2][1]
    assert "DIAGNOSTIC report" in prompts[3][1]
    conn.close()


def test_expired_assignment_is_recovered_once_then_cancelled():
    conn = connect(); seed_ops(conn)
    incident = ingest_signal(conn, source="runtime", title="Interrupted agent", severity="HIGH")
    agent = conn.execute("SELECT id FROM ops_agents WHERE role='LEAD'").fetchone()
    assignment_id = conn.execute(
        "INSERT INTO ops_agent_assignments(incident_id,agent_id,assignment,status,attempt_count,lease_expires_at,created_at) VALUES(?,?,?,'ACTIVE',1,?,?)",
        (incident["id"], agent["id"], "triage", "2000-01-01T00:00:00+00:00", utcnow_iso()),
    ).lastrowid
    assert recover_expired_assignments(conn) == 1
    assert conn.execute("SELECT status FROM ops_agent_assignments WHERE id=?", (assignment_id,)).fetchone()["status"] == "PENDING"
    conn.execute("UPDATE ops_agent_assignments SET status='ACTIVE',attempt_count=2,lease_expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (assignment_id,))
    recover_expired_assignments(conn)
    assert conn.execute("SELECT status FROM ops_agent_assignments WHERE id=?", (assignment_id,)).fetchone()["status"] == "CANCELLED"
    conn.close()


def test_ops_tick_retries_only_incident_missing_a_completed_role(monkeypatch):
    from beresin.config import settings
    from beresin.main import _ops_tick
    conn = connect(); seed_ops(conn)
    incident = ingest_signal(conn, source="runtime", title="Partial role failure", severity="LOW")
    # PostgreSQL integration mode enables Redis. Seed the worker liveness row
    # so this focused retry test doesn't also dispatch a meta-monitor incident.
    conn.execute(
        "INSERT INTO ops_policies(key,value_json,updated_at) VALUES(?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",
        ("worker.conversation.heartbeat", '{"status":"ok"}', utcnow_iso()),
    )
    for role, status in (("LEAD", "CANCELLED"), ("SECURITY", "COMPLETED"), ("DIAGNOSTIC", "COMPLETED")):
        agent = conn.execute("SELECT id FROM ops_agents WHERE role=?", (role,)).fetchone()
        conn.execute("INSERT INTO ops_agent_assignments(incident_id,agent_id,assignment,status,created_at) VALUES(?,?,?,?,?)", (incident["id"], agent["id"], role, status, utcnow_iso()))
    conn.commit(); conn.close()
    dispatched = []
    monkeypatch.setattr(settings, "ops_agents_enabled", True)
    monkeypatch.setattr("beresin.ops_runtime.dispatch_incident", lambda conn, incident_id: dispatched.append(incident_id) or [])
    _ops_tick()
    assert dispatched == [incident["id"]]


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
    notification = conn.execute("SELECT delivery_status,attempt_count,next_attempt_at FROM ops_notifications WHERE delivery_status='FAILED' ORDER BY id DESC LIMIT 1").fetchone()
    assert notification["attempt_count"] == 1
    assert notification["next_attempt_at"]
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


def test_cancelled_clean_worktree_can_be_removed_without_deleting_branch(tmp_path, monkeypatch):
    repo = tmp_path / "repo"; repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "ops@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Ops Test"], cwd=repo, check=True)
    (repo / "app.txt").write_text("before\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True)
    from beresin.config import settings
    monkeypatch.setattr(settings, "ops_worktree_root", str(tmp_path / "worktrees"))
    conn = connect(); incident, approval = _incident_and_approval(conn)
    change = provision_worktree(conn, incident["id"], approval["approval_id"], repo_root=repo)
    worktree = Path(change["worktree_path"])
    cancelled = cancel_code_change(conn, change["id"], _actor(conn))
    assert cancelled["status"] == "CANCELLED"
    cleaned = cleanup_code_worktree(conn, change["id"], repo_root=repo)
    assert cleaned["removed"] is True and not worktree.exists()
    assert subprocess.run(["git", "show-ref", "--verify", f"refs/heads/{change['branch_name']}"], cwd=repo, capture_output=True).returncode == 0
    conn.close()


def test_deployment_uses_second_approval_and_rolls_back(monkeypatch):
    conn = connect(); incident, fix = _incident_and_approval(conn)
    now = utcnow_iso()
    change_id = conn.execute("INSERT INTO ops_code_changes(incident_id,approval_id,branch_name,worktree_path,base_commit,commit_sha,status,created_at,updated_at) VALUES(?,?,?,?,?,?,'READY_FOR_REVIEW',?,?)", (incident["id"], fix["approval_id"], "ops/test", "/tmp/test", "base", "artifact123", now, now)).lastrowid
    for name in ("backend", "agent", "javascript-app", "javascript-chat", "javascript-supervisor", "diff-integrity", "security-bandit"):
        conn.execute("INSERT INTO ops_check_runs(code_change_id,name,status) VALUES(?,?,'PASSED')", (change_id, name))
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
