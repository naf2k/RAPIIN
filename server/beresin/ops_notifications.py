"""Remote owner notifications. Database remains the source of truth."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from .config import settings
from .database import utcnow_iso


def telegram_configured() -> bool:
    return bool(settings.ops_telegram_bot_token and settings.ops_telegram_chat_id)


def notify_owner(incident: dict) -> dict:
    """Send sanitized incident metadata; never send evidence or approval links with tokens."""
    if not telegram_configured():
        return {"status": "SKIPPED", "reason": "telegram_not_configured"}
    incident_url = f"{settings.ops_public_base_url.rstrip('/')}/supervisor/operations.html?incident={incident['id']}"
    text = (
        f"BERESIN {incident['severity']} — {incident['title']}\n"
        f"Status: {incident['status']}\n"
        f"Ringkasan: {(incident.get('summary') or 'Tidak ada ringkasan')[:800]}\n"
        f"Review: {incident_url}\n"
        "Keputusan hanya dapat dilakukan setelah login di Operations Center."
    )
    payload = urllib.parse.urlencode({"chat_id": settings.ops_telegram_chat_id, "text": text, "disable_web_page_preview": "true"}).encode()
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{settings.ops_telegram_bot_token}/sendMessage",
        data=payload,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            result = json.loads(response.read().decode())
        return {"status": "SENT" if result.get("ok") else "FAILED"}
    except Exception as exc:  # noqa: BLE001 - notification failure cannot break incident storage
        return {"status": "FAILED", "reason": type(exc).__name__}


def deliver_pending(conn, limit: int = 10) -> list[dict]:
    rows = conn.execute(
        """SELECT n.*, i.title incident_title, i.status incident_status, i.summary incident_summary
           FROM ops_notifications n LEFT JOIN ops_incidents i ON i.id=n.incident_id
           WHERE n.delivery_status='PENDING' ORDER BY n.id LIMIT ?""", (limit,),
    ).fetchall()
    results = []
    for row in rows:
        incident = {"id": row["incident_id"], "title": row["incident_title"] or row["title"], "severity": row["severity"], "status": row["incident_status"] or "OPEN", "summary": row["incident_summary"] or row["body"]}
        result = notify_owner(incident)
        conn.execute(
            "UPDATE ops_notifications SET delivery_status=?,delivered_at=?,last_error=? WHERE id=?",
            (result["status"], utcnow_iso() if result["status"] == "SENT" else None, result.get("reason"), row["id"]),
        )
        results.append({"notification_id": row["id"], **result})
    return results
