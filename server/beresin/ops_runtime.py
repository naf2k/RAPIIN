"""Durable role orchestration using the pinned official Hermes CLI."""
from __future__ import annotations

import json
import os
import subprocess
import shutil
import time
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import settings
from .database import utcnow_iso
from .ops_incidents import _event, get_incident, seed_ops
from .ops_adapter import OpsToolGateway
from .ops_safety import sanitize_text

READ_ONLY_ROLES = {"LEAD", "SECURITY", "DIAGNOSTIC"}
ROLE_PROMPTS = {
    "LEAD": "Ringkas dampak, confidence, kemungkinan penyebab, dan tindakan aman. Jangan menjalankan perubahan.",
    "SECURITY": "Nilai risiko keamanan, kemungkinan penyalahgunaan, dan containment. Jangan mengubah file atau sistem.",
    "DIAGNOSTIC": "Analisis bukti yang diberikan dan usulkan langkah reproduksi read-only. Jangan mengubah file atau sistem.",
}


def read_usage_report(path: Path) -> dict:
    """Parse Hermes usage output defensively; malformed reports count as zero."""
    empty = {"input_tokens": 0, "output_tokens": 0, "api_calls": 0, "estimated_cost_usd": 0.0}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        usage = raw.get("usage", raw) if isinstance(raw, dict) else {}

        def number(*keys, default=0):
            for key in keys:
                value = usage.get(key)
                if isinstance(value, (int, float)) and value >= 0:
                    return value
            return default

        return {
            "input_tokens": int(number("input_tokens", "prompt_tokens")),
            "output_tokens": int(number("output_tokens", "completion_tokens")),
            "api_calls": int(number("api_calls", "requests")),
            "estimated_cost_usd": float(number("estimated_cost_usd", "estimated_cost", "cost_usd", default=0.0)),
        }
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return empty


def _record_usage(conn, row, duration: int, prompt: str, output: str, status: str, usage: dict) -> None:
    conn.execute(
        """INSERT INTO ops_agent_usage(
               agent_id,incident_id,duration_ms,prompt_chars,output_chars,input_tokens,
               output_tokens,api_calls,estimated_cost_usd,status,created_at
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (row["agent_id"], row["incident_id"], duration, len(prompt), len(output),
         usage["input_tokens"], usage["output_tokens"], usage["api_calls"],
         usage["estimated_cost_usd"], status, utcnow_iso()),
    )


def hermes_process_environment(profile: str = "shared") -> dict:
    """Create a private profile without persisting the provider credential."""
    safe_profile = profile.strip().lower()
    if safe_profile not in {"lead", "security", "diagnostic", "coder", "shared"}:
        raise ValueError("Profile Operations Hermes tidak valid.")
    home = settings.data_dir / "ops-hermes" / safe_profile
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    config = home / "config.yaml"
    config.write_text(
        "model:\n"
        f"  default: {settings.ai_model}\n"
        "  provider: custom\n"
        f"  base_url: {settings.ai_base_url}\n"
        "terminal:\n  backend: local\n",
        encoding="utf-8",
    )
    # Older pilot builds wrote a plaintext provider key here. Remove that
    # compatibility artifact and inject the credential into this process only.
    env_file = home / ".env"
    env_file.unlink(missing_ok=True)
    config.chmod(0o600)
    env = os.environ.copy()
    env.update({
        "HERMES_HOME": str(home), "HERMES_CONFIG": str(config),
        "OPENAI_BASE_URL": settings.ai_base_url,
        "OPENAI_API_KEY": settings.ai_api_key,
    })
    env.pop("HERMES_ENV", None)
    return env


def _agent(conn, role: str):
    seed_ops(conn)
    return conn.execute("SELECT * FROM ops_agents WHERE role=?", (role,)).fetchone()


def assign_default_roles(conn, incident_id: int) -> list[int]:
    ids = []
    now = utcnow_iso()
    for role in ("LEAD", "SECURITY", "DIAGNOSTIC"):
        agent = _agent(conn, role)
        attempt_count = conn.execute("SELECT COUNT(*) n FROM ops_agent_assignments WHERE incident_id=? AND agent_id=?", (incident_id, agent["id"])).fetchone()["n"]
        exists = conn.execute("SELECT id FROM ops_agent_assignments WHERE incident_id=? AND agent_id=? AND status IN ('PENDING','ACTIVE','COMPLETED')", (incident_id, agent["id"])).fetchone()
        if not exists and attempt_count < 2:
            ids.append(conn.execute(
                "INSERT INTO ops_agent_assignments(incident_id,agent_id,assignment,status,created_at) VALUES(?,?,?,'PENDING',?)",
                (incident_id, agent["id"], f"{role} analysis", now),
            ).lastrowid)
    return ids


def _daily_budget_available(conn) -> bool:
    count = conn.execute("SELECT COUNT(*) n FROM ops_agent_usage WHERE created_at >= datetime('now','start of day')").fetchone()["n"]
    cost = conn.execute("SELECT COALESCE(SUM(estimated_cost_usd),0) n FROM ops_agent_usage WHERE created_at >= datetime('now','start of day')").fetchone()["n"]
    return count < settings.ops_agent_daily_run_limit and cost < settings.ops_agent_daily_cost_limit_usd


def provider_circuit_open(conn) -> bool:
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=settings.ops_agent_circuit_cooldown_seconds)).isoformat()
    failures = conn.execute("SELECT COUNT(*) n FROM ops_agent_usage WHERE status='FAILED' AND created_at >= ?", (cutoff,)).fetchone()["n"]
    return failures >= settings.ops_agent_failure_threshold


def run_assignment(conn, assignment_id: int, runner=None) -> dict:
    row = conn.execute(
        """SELECT a.*, g.role, g.name agent_name FROM ops_agent_assignments a
           JOIN ops_agents g ON g.id=a.agent_id WHERE a.id=?""", (assignment_id,),
    ).fetchone()
    if not row:
        raise LookupError("Assignment tidak ditemukan.")
    if row["status"] != "PENDING":
        raise ValueError("Assignment sudah diproses.")
    if row["role"] not in READ_ONLY_ROLES:
        raise PermissionError("Hanya assignment read-only yang dapat dijalankan tanpa approval code fix.")
    if not _daily_budget_available(conn):
        raise RuntimeError("Batas agent harian tercapai.")
    if provider_circuit_open(conn):
        raise RuntimeError("Circuit breaker provider Operations Agent sedang terbuka.")
    active = conn.execute("SELECT COUNT(*) n FROM ops_agent_assignments WHERE status='ACTIVE'").fetchone()["n"]
    if active >= settings.ops_agent_max_concurrency:
        raise RuntimeError("Batas concurrency Operations Agent tercapai.")
    gateway = OpsToolGateway(conn, row["role"], row["incident_id"])
    incident = gateway.get_incident()
    prior_reports = gateway.list_reports()
    prompt = (
        "Anda adalah agent Operations Center BERESIN. " + ROLE_PROMPTS[row["role"]] + "\n"
        "Balas Bahasa Indonesia dalam JSON dengan keys summary, findings, recommendation, confidence.\n"
        "Data insiden tersanitasi:\n" + json.dumps({k: incident.get(k) for k in ("id", "title", "severity", "status", "summary", "source", "affected_resource", "occurrence_count")}, ensure_ascii=False) +
        "\nLaporan agent sebelumnya:\n" + json.dumps(prior_reports, ensure_ascii=False)
    )
    started = time.monotonic()
    lease = (datetime.now(timezone.utc) + timedelta(seconds=settings.ops_agent_timeout_seconds + 30)).isoformat()
    conn.execute("UPDATE ops_agent_assignments SET status='ACTIVE',attempt_count=attempt_count+1,lease_expires_at=? WHERE id=?", (lease, assignment_id))
    conn.execute("UPDATE ops_agents SET state='RUNNING',updated_at=? WHERE id=?", (utcnow_iso(), row["agent_id"]))
    conn.commit()
    usage = {"input_tokens": 0, "output_tokens": 0, "api_calls": 0, "estimated_cost_usd": 0.0}
    usage_path = None
    try:
        if runner:
            output = runner(row["role"], prompt)
        elif not settings.ops_agents_enabled:
            raise RuntimeError("Runtime Hermes belum diaktifkan oleh OPS_AGENTS_ENABLED.")
        else:
            hermes_command = shutil.which(settings.ops_hermes_command) or str(Path.home() / ".local/bin/hermes")
            if not Path(hermes_command).is_file():
                raise RuntimeError("Hermes CLI tidak ditemukan oleh service account.")
            usage_dir = settings.data_dir / "ops-hermes" / row["role"].lower()
            usage_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            handle = tempfile.NamedTemporaryFile(prefix="usage-", suffix=".json", dir=usage_dir, delete=False)
            usage_path = Path(handle.name)
            handle.close()
            command = [hermes_command, "--safe-mode", "--cli", "--usage-file", str(usage_path), "--provider", "custom", "-m", settings.ai_model, "-z", prompt]
            completed = subprocess.run(command, cwd=str(settings.data_dir), capture_output=True, text=True, timeout=settings.ops_agent_timeout_seconds, check=False, env=hermes_process_environment(row["role"]))
            usage = read_usage_report(usage_path)
            combined = (completed.stdout or "") + "\n" + (completed.stderr or "")
            if completed.returncode or "HTTP 4" in combined or "Error from provider" in combined:
                raise RuntimeError(f"Hermes exit {completed.returncode}: {(completed.stderr or '')[-500:]}")
            output = completed.stdout.strip()
        report = gateway.submit_report(output)
        output = json.dumps(report, ensure_ascii=False)
        duration = int((time.monotonic() - started) * 1000)
        conn.execute("UPDATE ops_agent_assignments SET status='COMPLETED',completed_at=?,lease_expires_at=NULL WHERE id=?", (utcnow_iso(), assignment_id))
        _record_usage(conn, row, duration, prompt, output, "SUCCEEDED", usage)
        status = "COMPLETED"
    except Exception as exc:
        output = sanitize_text(f"{type(exc).__name__}: {exc}", 1000)
        duration = int((time.monotonic() - started) * 1000)
        conn.execute("UPDATE ops_agent_assignments SET status='CANCELLED',completed_at=?,lease_expires_at=NULL WHERE id=?", (utcnow_iso(), assignment_id))
        conn.execute("INSERT INTO ops_agent_messages(incident_id,sender_agent_id,message_type,content,created_at) VALUES(?,?,'ERROR',?,?)", (row["incident_id"], row["agent_id"], output, utcnow_iso()))
        if usage_path:
            usage = read_usage_report(usage_path)
        _record_usage(conn, row, duration, prompt, output, "FAILED", usage)
        status = "FAILED"
    finally:
        if usage_path:
            usage_path.unlink(missing_ok=True)
        conn.execute("UPDATE ops_agents SET state='IDLE',updated_at=? WHERE id=?", (utcnow_iso(), row["agent_id"]))
    return {"assignment_id": assignment_id, "status": status, "output": output}


def dispatch_incident(conn, incident_id: int, runner=None) -> list[dict]:
    ids = assign_default_roles(conn, incident_id)
    results = [run_assignment(conn, assignment_id, runner=runner) for assignment_id in ids]
    completed_roles = {
        row["role"] for row in conn.execute(
            "SELECT DISTINCT g.role FROM ops_agent_assignments a JOIN ops_agents g ON g.id=a.agent_id WHERE a.incident_id=? AND a.status='COMPLETED'",
            (incident_id,),
        ).fetchall()
    }
    synthesis = conn.execute("SELECT id,status FROM ops_agent_assignments WHERE incident_id=? AND assignment='LEAD synthesis' ORDER BY id DESC LIMIT 1", (incident_id,)).fetchone()
    if completed_roles >= READ_ONLY_ROLES and not synthesis:
        lead = _agent(conn, "LEAD")
        synthesis_id = conn.execute(
            "INSERT INTO ops_agent_assignments(incident_id,agent_id,assignment,status,created_at) VALUES(?,?,?,'PENDING',?)",
            (incident_id, lead["id"], "LEAD synthesis", utcnow_iso()),
        ).lastrowid
        results.append(run_assignment(conn, synthesis_id, runner=runner))
    finalize_agent_triage(conn, incident_id)
    return results


def finalize_agent_triage(conn, incident_id: int) -> bool:
    roles = conn.execute(
        "SELECT DISTINCT g.role FROM ops_agent_assignments a JOIN ops_agents g ON g.id=a.agent_id "
        "WHERE a.incident_id=? AND a.status='COMPLETED'",
        (incident_id,),
    ).fetchall()
    synthesis = conn.execute("SELECT 1 FROM ops_agent_assignments WHERE incident_id=? AND assignment='LEAD synthesis' AND status='COMPLETED'", (incident_id,)).fetchone()
    if {row["role"] for row in roles} >= READ_ONLY_ROLES and synthesis:
        exists = conn.execute("SELECT 1 FROM ops_incident_events WHERE incident_id=? AND event_type='AGENT_TRIAGE_COMPLETED'", (incident_id,)).fetchone()
        if not exists:
            now = utcnow_iso()
            conn.execute("UPDATE ops_incidents SET status='INVESTIGATING',updated_at=? WHERE id=? AND status='OPEN'", (now, incident_id))
            synthesis_report = conn.execute(
                """SELECT m.content,g.id agent_id FROM ops_agent_messages m
                   JOIN ops_agents g ON g.id=m.sender_agent_id
                   JOIN ops_agent_assignments a ON a.incident_id=m.incident_id AND a.agent_id=g.id
                   WHERE m.incident_id=? AND g.role='LEAD' AND a.assignment='LEAD synthesis'
                     AND m.message_type='REPORT' ORDER BY m.id DESC LIMIT 1""",
                (incident_id,),
            ).fetchone()
            if synthesis_report:
                try:
                    report = json.loads(synthesis_report["content"])
                except json.JSONDecodeError:
                    report = {}
                conn.execute(
                    """INSERT INTO ops_action_proposals
                       (incident_id,proposed_by_agent_id,action_type,title,description,risk,status,created_at,updated_at)
                       VALUES(?,?,'INVESTIGATION',?,?,?,'PENDING',?,?)""",
                    (incident_id, synthesis_report["agent_id"], "Tinjau rekomendasi Lead",
                     sanitize_text(str(report.get("recommendation") or report.get("summary") or "Review manual diperlukan."), 8000),
                     sanitize_text("Read-only review; code change dan deployment tetap membutuhkan approval terpisah.", 2000), now, now),
                )
            _event(conn, incident_id, "AGENT_TRIAGE_COMPLETED", "Lead", "LEAD", {"roles": sorted(READ_ONLY_ROLES)})
            incident = get_incident(conn, incident_id)
            conn.execute(
                "INSERT INTO ops_notifications(incident_id,title,body,severity,created_at) VALUES(?,?,?,?,?)",
                (incident_id, f"Analisis agent selesai: {incident['title']}", "Review laporan Lead, Security, dan Diagnostic di Operations Center.", incident["severity"], now),
            )
        return True
    return False


def recover_expired_assignments(conn) -> int:
    """Requeue one interrupted attempt; cancel assignments interrupted twice."""
    now = utcnow_iso()
    rows = conn.execute(
        "SELECT id,attempt_count FROM ops_agent_assignments WHERE status='ACTIVE' AND lease_expires_at < ?",
        (now,),
    ).fetchall()
    for row in rows:
        if row["attempt_count"] >= 2:
            conn.execute("UPDATE ops_agent_assignments SET status='CANCELLED',completed_at=?,lease_expires_at=NULL WHERE id=?", (now, row["id"]))
        else:
            conn.execute("UPDATE ops_agent_assignments SET status='PENDING',lease_expires_at=NULL WHERE id=?", (row["id"],))
    return len(rows)
