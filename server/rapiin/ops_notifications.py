"""Remote owner notifications. Database remains the source of truth."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from .config import settings
from .database import utcnow_iso
from .ops_safety import sanitize_text

SEVERITY_COPY = {
    "CRITICAL": ("🔴", "Sangat penting", "Layanan dapat berhenti, data berisiko, atau keamanan dapat terdampak."),
    "HIGH": ("🟠", "Penting", "Sebagian fungsi RAPIIN mungkin terganggu dan perlu segera diperiksa."),
    "MEDIUM": ("🟡", "Perlu diperhatikan", "Gangguan masih terbatas, tetapi perlu dipantau agar tidak membesar."),
    "LOW": ("🔵", "Informasi", "Belum ada gangguan besar. Informasi ini dicatat untuk pemantauan."),
}

STATUS_COPY = {
    "OPEN": "Masalah baru terdeteksi dan sudah dicatat.",
    "INVESTIGATING": "AI Operations sedang memeriksa penyebab dan dampaknya.",
    "AWAITING_APPROVAL": "Pemeriksaan selesai dan keputusan Anda dibutuhkan sebelum tindakan dijalankan.",
    "APPROVED_FOR_FIX": "Perbaikan kode sudah disetujui dan akan dikerjakan di ruang terisolasi.",
    "FIX_IN_PROGRESS": "Coder sedang menyiapkan perbaikan di ruang terisolasi.",
    "AWAITING_DEPLOY_APPROVAL": "Perbaikan sudah diperiksa dan menunggu izin terpisah untuk diterapkan.",
    "RESOLVED": "Masalah sudah selesai dan kondisi telah diverifikasi kembali.",
    "ROLLED_BACK": "Perubahan dibatalkan dan sistem dikembalikan ke versi sebelumnya.",
    "FAILED": "Penanganan belum berhasil dan perlu diperiksa oleh operator.",
}


def telegram_message(incident: dict, incident_url: str) -> str:
    """Build beginner-friendly, sanitized owner copy without approval tokens."""
    severity = str(incident.get("severity") or "MEDIUM").upper()
    icon, severity_label, impact = SEVERITY_COPY.get(severity, SEVERITY_COPY["MEDIUM"])
    status = str(incident.get("status") or "OPEN").upper()
    status_text = STATUS_COPY.get(status, "AI Operations sudah mencatat perkembangan terbaru.")
    title = sanitize_text(str(incident.get("title") or "Masalah pada RAPIIN"), 200)
    summary = sanitize_text(str(incident.get("summary") or "Belum ada penjelasan tambahan."), 800)
    action = (
        "Buka halaman pemeriksaan, baca rekomendasi, lalu pilih Setujui atau Tolak. "
        "RAPIIN tidak akan menjalankan tindakan berisiko tanpa persetujuan Anda."
        if status in {"AWAITING_APPROVAL", "AWAITING_DEPLOY_APPROVAL"}
        else "Buka halaman pemeriksaan untuk melihat perkembangan. Untuk saat ini tidak ada tindakan otomatis berisiko."
    )
    return (
        f"{icon} Pemberitahuan RAPIIN — {severity_label}\n\n"
        f"Apa yang terjadi?\n{title}\n\n"
        f"Penjelasan singkat\n{summary}\n\n"
        f"Kemungkinan dampak\n{impact}\n\n"
        f"Apa yang sudah dilakukan?\n{status_text}\n\n"
        f"Apa yang perlu Anda lakukan?\n{action}\n\n"
        f"Lihat pemeriksaan lengkap:\n{incident_url}\n\n"
        "Catatan keamanan: keputusan hanya dapat diberikan setelah login ke Operations Center."
    )


def telegram_configured() -> bool:
    return bool(settings.ops_telegram_bot_token and settings.ops_telegram_chat_id)


def notify_owner(incident: dict) -> dict:
    """Send sanitized incident metadata; never send evidence or approval links with tokens."""
    if not telegram_configured():
        return {"status": "SKIPPED", "reason": "telegram_not_configured"}
    incident_url = f"{settings.ops_public_base_url.rstrip('/')}/supervisor/operations.html"
    if incident.get("id"):
        incident_url += f"?incident={incident['id']}"
    text = telegram_message(incident, incident_url)
    payload = urllib.parse.urlencode({"chat_id": settings.ops_telegram_chat_id, "text": text, "disable_web_page_preview": "true"}).encode()
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{settings.ops_telegram_bot_token}/sendMessage",
        data=payload,
        method="POST",
    )
    try:
        # URL origin is a hard-coded Telegram HTTPS endpoint; only the bot path
        # and form payload vary.
        with urllib.request.urlopen(request, timeout=10) as response:  # nosec B310
            result = json.loads(response.read().decode())
        return {"status": "SENT" if result.get("ok") else "FAILED"}
    except Exception as exc:  # noqa: BLE001 - notification failure cannot break incident storage
        return {"status": "FAILED", "reason": type(exc).__name__}


def deliver_pending(conn, limit: int = 10) -> list[dict]:
    """Send queued owner notifications without holding a transaction open.

    A Telegram request can block for its full 10s timeout. Keeping the read
    transaction open across that call trips PostgreSQL's
    `idle_in_transaction_session_timeout`, which terminates the connection and
    aborts the whole monitor tick, so the pending rows are read, the
    transaction is closed, and each result is committed on its own.
    """
    rows = conn.execute(
        """SELECT n.*, i.title incident_title, i.status incident_status, i.summary incident_summary
           FROM ops_notifications n LEFT JOIN ops_incidents i ON i.id=n.incident_id
           WHERE (n.delivery_status='PENDING' OR (n.delivery_status='FAILED' AND n.next_attempt_at <= ?))
             AND n.attempt_count < 3 ORDER BY n.id LIMIT ?""", (utcnow_iso(), limit),
    ).fetchall()
    conn.commit()
    results = []
    for row in rows:
        incident = {"id": row["incident_id"], "title": row["incident_title"] or row["title"], "severity": row["severity"], "status": row["incident_status"] or "OPEN", "summary": row["incident_summary"] or row["body"]}
        result = notify_owner(incident)
        attempts = row["attempt_count"] + (1 if result["status"] in {"SENT", "FAILED"} else 0)
        retry_at = None
        if result["status"] == "FAILED" and attempts < 3:
            retry_at = (datetime.now(timezone.utc) + timedelta(minutes=(1, 5, 15)[attempts - 1])).isoformat()
        conn.execute(
            "UPDATE ops_notifications SET delivery_status=?,delivered_at=?,last_error=?,attempt_count=?,next_attempt_at=? WHERE id=?",
            (result["status"], utcnow_iso() if result["status"] == "SENT" else None, result.get("reason"), attempts, retry_at, row["id"]),
        )
        conn.commit()
        results.append({"notification_id": row["id"], **result})
    return results
