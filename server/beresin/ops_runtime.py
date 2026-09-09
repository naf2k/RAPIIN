"""Durable role orchestration using the pinned official Hermes CLI."""
from __future__ import annotations

import json
import os
import subprocess
import shutil
import time
from pathlib import Path

from .config import settings
from .database import utcnow_iso
from .ops_incidents import get_incident, seed_ops

READ_ONLY_ROLES = {"LEAD", "SECURITY", "DIAGNOSTIC"}
ROLE_PROMPTS = {
    "LEAD": "Ringkas dampak, confidence, kemungkinan penyebab, dan tindakan aman. Jangan menjalankan perubahan.",
    "SECURITY": "Nilai risiko keamanan, kemungkinan penyalahgunaan, dan containment. Jangan mengubah file atau sistem.",
    "DIAGNOSTIC": "Analisis bukti yang diberikan dan usulkan langkah reproduksi read-only. Jangan mengubah file atau sistem.",
}


def hermes_process_environment() -> dict:
    """Create a private, BERESIN-only Hermes profile for its working provider."""
    home = settings.data_dir / "ops-hermes"
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    config = home / "config.yaml"
    env_file = home / ".env"
    config.write_text(
        "model:\n"
        f"  default: {settings.ai_model}\n"
        "  provider: custom\n"
        f"  base_url: {settings.ai_base_url}\n"
        "terminal:\n  backend: local\n",
        encoding="utf-8",
    )
    env_file.write_text(
        f"OPENAI_BASE_URL={settings.ai_base_url}\nOPENAI_API_KEY={settings.ai_api_key}\n",
        encoding="utf-8",
    )
    config.chmod(0o600); env_file.chmod(0o600)
    env = os.environ.copy()
    env.update({"HERMES_HOME": str(home), "HERMES_CONFIG": str(config), "HERMES_ENV": str(env_file)})
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
    return count < settings.ops_agent_daily_run_limit


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
    incident = get_incident(conn, row["incident_id"])
    prompt = (
        "Anda adalah agent Operations Center BERESIN. " + ROLE_PROMPTS[row["role"]] + "\n"
        "Balas Bahasa Indonesia dalam JSON dengan keys summary, findings, recommendation, confidence.\n"
        "Data insiden tersanitasi:\n" + json.dumps({k: incident.get(k) for k in ("id", "title", "severity", "status", "summary", "source", "affected_resource", "occurrence_count")}, ensure_ascii=False)
    )
    started = time.monotonic()
    conn.execute("UPDATE ops_agent_assignments SET status='ACTIVE' WHERE id=?", (assignment_id,))
    conn.execute("UPDATE ops_agents SET state='RUNNING',updated_at=? WHERE id=?", (utcnow_iso(), row["agent_id"]))
    conn.commit()
    try:
        if runner:
            output = runner(row["role"], prompt)
        elif not settings.ops_agents_enabled:
            raise RuntimeError("Runtime Hermes belum diaktifkan oleh OPS_AGENTS_ENABLED.")
        else:
            hermes_command = shutil.which(settings.ops_hermes_command) or str(Path.home() / ".local/bin/hermes")
            if not Path(hermes_command).is_file():
                raise RuntimeError("Hermes CLI tidak ditemukan oleh service account.")
            command = [hermes_command, "--safe-mode", "--cli", "--provider", "custom", "-m", settings.ai_model, "-z", prompt]
            completed = subprocess.run(command, cwd=str(settings.data_dir), capture_output=True, text=True, timeout=settings.ops_agent_timeout_seconds, check=False, env=hermes_process_environment())
            combined = (completed.stdout or "") + "\n" + (completed.stderr or "")
            if completed.returncode or "HTTP 4" in combined or "Error from provider" in combined:
                raise RuntimeError(f"Hermes exit {completed.returncode}: {(completed.stderr or '')[-500:]}")
            output = completed.stdout.strip()
        duration = int((time.monotonic() - started) * 1000)
        conn.execute("INSERT INTO ops_agent_messages(incident_id,sender_agent_id,message_type,content,created_at) VALUES(?,?,'REPORT',?,?)", (row["incident_id"], row["agent_id"], output[:20000], utcnow_iso()))
        conn.execute("UPDATE ops_agent_assignments SET status='COMPLETED',completed_at=? WHERE id=?", (utcnow_iso(), assignment_id))
        conn.execute("INSERT INTO ops_agent_usage(agent_id,incident_id,duration_ms,prompt_chars,output_chars,status,created_at) VALUES(?,?,?,?,?,'SUCCEEDED',?)", (row["agent_id"], row["incident_id"], duration, len(prompt), len(output), utcnow_iso()))
        status = "COMPLETED"
    except Exception as exc:
        output = f"{type(exc).__name__}: {str(exc)[:1000]}"
        duration = int((time.monotonic() - started) * 1000)
        conn.execute("UPDATE ops_agent_assignments SET status='CANCELLED',completed_at=? WHERE id=?", (utcnow_iso(), assignment_id))
        conn.execute("INSERT INTO ops_agent_messages(incident_id,sender_agent_id,message_type,content,created_at) VALUES(?,?,'ERROR',?,?)", (row["incident_id"], row["agent_id"], output, utcnow_iso()))
        conn.execute("INSERT INTO ops_agent_usage(agent_id,incident_id,duration_ms,prompt_chars,output_chars,status,created_at) VALUES(?,?,?,?,?,'FAILED',?)", (row["agent_id"], row["incident_id"], duration, len(prompt), len(output), utcnow_iso()))
        status = "FAILED"
    finally:
        conn.execute("UPDATE ops_agents SET state='IDLE',updated_at=? WHERE id=?", (utcnow_iso(), row["agent_id"]))
    return {"assignment_id": assignment_id, "status": status, "output": output}


def dispatch_incident(conn, incident_id: int, runner=None) -> list[dict]:
    ids = assign_default_roles(conn, incident_id)
    return [run_assignment(conn, assignment_id, runner=runner) for assignment_id in ids]
