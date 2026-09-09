"""Role-scoped tool gateway used by Operations Agent runtimes.

The adapter is the authorization boundary. Model prompts never receive a raw
database connection and callers cannot select capabilities outside their role.
"""
from __future__ import annotations

import json

from .database import utcnow_iso
from .ops_safety import parse_agent_report, sanitize

ROLE_TOOLS = {
    "LEAD": {"get_incident", "list_reports", "submit_report", "send_message", "get_approval_status"},
    "SECURITY": {"get_incident", "list_evidence", "list_reports", "submit_report", "send_message"},
    "DIAGNOSTIC": {"get_incident", "list_evidence", "list_reports", "submit_report", "send_message"},
    "CODER": {"get_incident", "list_reports", "get_approval_status"},
}


class OpsToolGateway:
    def __init__(self, conn, role: str, incident_id: int):
        role = role.upper()
        if role not in ROLE_TOOLS:
            raise PermissionError("Role Operations tidak valid.")
        self.conn, self.role, self.incident_id = conn, role, incident_id
        self.agent = conn.execute("SELECT * FROM ops_agents WHERE role=?", (role,)).fetchone()
        if not self.agent:
            raise PermissionError("Identitas agent belum terdaftar.")

    def _require(self, tool: str) -> None:
        if tool not in ROLE_TOOLS[self.role]:
            raise PermissionError(f"Tool {tool} tidak diizinkan untuk {self.role}.")

    def get_incident(self) -> dict:
        self._require("get_incident")
        row = self.conn.execute("SELECT * FROM ops_incidents WHERE id=?", (self.incident_id,)).fetchone()
        if not row:
            raise LookupError("Incident tidak ditemukan.")
        allowed = ("id", "title", "severity", "status", "summary", "source", "affected_resource", "occurrence_count")
        return sanitize({key: row[key] for key in allowed})

    def list_evidence(self) -> list[dict]:
        self._require("list_evidence")
        rows = self.conn.execute("SELECT id,kind,source,content_json,content_hash,created_at FROM ops_evidence WHERE incident_id=? ORDER BY id", (self.incident_id,)).fetchall()
        return [{**{key: row[key] for key in ("id", "kind", "source", "content_hash", "created_at")}, "content": sanitize(json.loads(row["content_json"]))} for row in rows]

    def list_reports(self, limit: int = 3) -> list[dict]:
        self._require("list_reports")
        rows = self.conn.execute("SELECT content FROM ops_agent_messages WHERE incident_id=? AND message_type='REPORT' ORDER BY id DESC LIMIT ?", (self.incident_id, min(max(limit, 1), 10))).fetchall()
        reports = []
        for row in reversed(rows):
            try:
                reports.append(sanitize(json.loads(row["content"])))
            except json.JSONDecodeError:
                continue
        return reports

    def submit_report(self, output: str) -> dict:
        self._require("submit_report")
        report = parse_agent_report(output)
        content = json.dumps(report, ensure_ascii=False)
        self.conn.execute("INSERT INTO ops_agent_messages(incident_id,sender_agent_id,message_type,content,created_at) VALUES(?,?,'REPORT',?,?)", (self.incident_id, self.agent["id"], content, utcnow_iso()))
        return report

    def send_message(self, recipient_role: str, message_type: str, content: dict) -> int:
        self._require("send_message")
        recipient = self.conn.execute("SELECT id FROM ops_agents WHERE role=?", (recipient_role.upper(),)).fetchone()
        if not recipient:
            raise LookupError("Agent tujuan tidak ditemukan.")
        return self.conn.execute(
            "INSERT INTO ops_agent_messages(incident_id,sender_agent_id,recipient_agent_id,message_type,content,created_at) VALUES(?,?,?,?,?,?)",
            (self.incident_id, self.agent["id"], recipient["id"], message_type[:50], json.dumps(sanitize(content), ensure_ascii=False), utcnow_iso()),
        ).lastrowid

    def get_approval_status(self) -> list[dict]:
        self._require("get_approval_status")
        return [dict(row) for row in self.conn.execute("SELECT id,approval_type,status,requested_at,expires_at FROM ops_approvals WHERE incident_id=? ORDER BY id", (self.incident_id,)).fetchall()]
