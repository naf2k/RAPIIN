import urllib.parse

from rapiin.ops_notifications import telegram_message


def test_telegram_message_is_clear_for_nontechnical_owner():
    message = telegram_message(
        {
            "id": 42,
            "severity": "HIGH",
            "status": "INVESTIGATING",
            "title": "Desktop agent offline",
            "summary": "Satu komputer tidak mengirim kabar ke server.",
        },
        "https://rapiin.example.com/supervisor/operations.html?incident=42",
    )
    for heading in (
        "Apa yang terjadi?",
        "Penjelasan singkat",
        "Kemungkinan dampak",
        "Apa yang sudah dilakukan?",
        "Apa yang perlu Anda lakukan?",
    ):
        assert heading in message
    assert "sedang memeriksa penyebab" in message
    assert "tidak ada tindakan otomatis berisiko" in message
    assert "incident=42" in message


def test_approval_notification_explains_owner_choice_and_safety():
    message = telegram_message(
        {"severity": "CRITICAL", "status": "AWAITING_APPROVAL", "title": "Perbaikan tersedia", "summary": "Perlu keputusan owner."},
        "https://rapiin.example.com/review",
    )
    assert "pilih Setujui atau Tolak" in message
    assert "tidak akan menjalankan tindakan berisiko tanpa persetujuan" in message
    assert "setelah login" in message


def test_notification_payload_contains_friendly_copy(monkeypatch):
    from rapiin.config import settings
    from rapiin.ops_notifications import notify_owner

    monkeypatch.setattr(settings, "ops_telegram_bot_token", "fake-token")
    monkeypatch.setattr(settings, "ops_telegram_chat_id", "123")
    captured = {}

    class Response:
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def read(self): return b'{"ok":true}'

    def fake_open(request, timeout):
        captured.update(urllib.parse.parse_qs(request.data.decode()))
        assert timeout == 10
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_open)
    result = notify_owner({"id": 7, "severity": "HIGH", "status": "OPEN", "title": "Queue tertunda", "summary": "Pekerjaan menunggu lebih lama."})
    assert result == {"status": "SENT"}
    assert "Apa yang terjadi?" in captured["text"][0]
    assert "disable_web_page_preview" not in captured["text"][0]


def test_deliver_pending_closes_transaction_before_network_call(monkeypatch):
    """Regression: the Telegram call ran inside an open transaction.

    Holding the read transaction across the 10s Telegram timeout tripped
    PostgreSQL's idle_in_transaction_session_timeout, which terminated the
    connection and aborted the monitor tick (observed as a 282s tick stall and
    a `FATAL: terminating connection due to idle-in-transaction timeout`).
    """
    from rapiin.ops_notifications import deliver_pending

    events = []

    class Cursor:
        def fetchall(self):
            return [{
                "id": 1, "incident_id": 5, "title": "t", "body": "b", "severity": "HIGH",
                "incident_title": "Incident", "incident_status": "OPEN", "incident_summary": "s",
                "attempt_count": 0, "next_attempt_at": None, "delivery_status": "PENDING",
            }]

    class Conn:
        def execute(self, query, params=()):
            events.append("execute")
            return Cursor()

        def commit(self):
            events.append("commit")

    def fake_notify(incident):
        events.append("network")
        return {"status": "SENT"}

    monkeypatch.setattr("rapiin.ops_notifications.notify_owner", fake_notify)
    results = deliver_pending(Conn())
    assert results and results[0]["status"] == "SENT"
    assert events.index("commit") < events.index("network"), "transaction must be closed before the network call"
    assert events[-1] == "commit", "the delivery result must be committed"
