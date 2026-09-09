import json

import pytest

from beresin.database import connect
from beresin.ops_adapter import OpsToolGateway
from beresin.ops_incidents import ingest_signal, seed_ops


def _gateway(role="LEAD"):
    conn = connect(); seed_ops(conn)
    incident = ingest_signal(conn, source="adapter-test", title="Bounded adapter", severity="HIGH", details={"token": "must-hide", "safe": "visible"})
    return conn, incident, OpsToolGateway(conn, role, incident["id"])


def test_role_scoped_gateway_hides_secrets_and_denies_evidence_to_lead():
    conn, incident, gateway = _gateway("LEAD")
    assert gateway.get_incident()["id"] == incident["id"]
    with pytest.raises(PermissionError):
        gateway.list_evidence()
    report = gateway.submit_report(json.dumps({"summary": "safe", "confidence": 0.9}))
    assert report["summary"] == "safe"
    conn.close()


def test_security_reads_only_sanitized_evidence_and_sends_structured_message():
    conn, _, gateway = _gateway("SECURITY")
    evidence = gateway.list_evidence()
    assert evidence[0]["content"]["token"] == "[REDACTED]"
    message_id = gateway.send_message("LEAD", "ANALYSIS_RESULT", {"token": "hidden", "finding": "safe"})
    stored = conn.execute("SELECT content,recipient_agent_id FROM ops_agent_messages WHERE id=?", (message_id,)).fetchone()
    assert "hidden" not in stored["content"]
    assert stored["recipient_agent_id"]
    with pytest.raises(PermissionError):
        gateway.get_approval_status()
    conn.close()


def test_coder_gateway_cannot_submit_or_message():
    conn, _, gateway = _gateway("CODER")
    with pytest.raises(PermissionError):
        gateway.submit_report('{"summary":"unsafe", "confidence":1}')
    with pytest.raises(PermissionError):
        gateway.send_message("LEAD", "RESULT", {})
    conn.close()
