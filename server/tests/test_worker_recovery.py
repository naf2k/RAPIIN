"""Host sleep/wake and dropped-connection resilience for the task worker.

A lost PostgreSQL connection (laptop sleep, database restart) must interrupt
work, not fail it permanently: the job is requeued and picked up again. Only a
non-connection error is a real task failure.
"""
import sqlite3

from rapiin.database import is_transient_db_error


class IdleInTransactionSessionTimeout(Exception):
    pass


class OperationalError(Exception):
    pass


def test_transient_db_error_classification():
    """Connection loss is retryable; a constraint error never is."""
    assert is_transient_db_error(IdleInTransactionSessionTimeout("terminating connection due to idle-in-transaction timeout"))
    assert is_transient_db_error(OperationalError("consuming input failed: server closed the connection unexpectedly"))
    assert is_transient_db_error(OperationalError("connection refused"))
    assert is_transient_db_error(sqlite3.OperationalError("database is locked"))
    assert not is_transient_db_error(ValueError("NOT NULL constraint failed: tasks.status"))
    assert not is_transient_db_error(KeyError("status"))


def _seed_job(conn, *, status: str, lease: str | None):
    from rapiin.database import utcnow_iso
    user_id = conn.execute("SELECT id FROM users LIMIT 1").fetchone()["id"]
    conv_id = conn.execute(
        "INSERT INTO conversations(user_id, title, created_at, updated_at) VALUES (?, 'c', ?, ?)",
        (user_id, utcnow_iso(), utcnow_iso()),
    ).lastrowid
    task_id = conn.execute(
        "INSERT INTO tasks(user_id, type, status, created_at) VALUES (?, 'conversation', 'RUNNING', ?)",
        (user_id, utcnow_iso()),
    ).lastrowid
    conn.execute(
        "INSERT INTO conversation_jobs(task_id, user_id, conversation_id, status, lease_expires_at, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (task_id, user_id, conv_id, status, lease, utcnow_iso()),
    )
    return task_id


def test_expired_claim_is_requeued_and_dispatched(monkeypatch):
    """A stale CLAIMED job (host slept mid-task) is resumed, not stranded."""
    from rapiin import worker
    from rapiin.database import db_session

    dispatched: list[int] = []
    monkeypatch.setattr(worker, "_dispatch_conversation_task", dispatched.append)

    with db_session() as conn:
        task_id = _seed_job(conn, status="CLAIMED", lease="2000-01-01T00:00:00+00:00")

    count = worker.requeue_stale_conversation_jobs()
    assert count == 1
    assert dispatched == [task_id]
    with db_session() as conn:
        row = conn.execute("SELECT status FROM conversation_jobs WHERE task_id = ?", (task_id,)).fetchone()
    assert row["status"] == "PENDING"


def test_healthy_claim_is_left_alone(monkeypatch):
    """A task holding a future lease is never flipped back to PENDING."""
    from datetime import datetime, timedelta, timezone

    from rapiin import worker
    from rapiin.database import db_session

    dispatched: list[int] = []
    monkeypatch.setattr(worker, "_dispatch_conversation_task", dispatched.append)
    future = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()

    with db_session() as conn:
        task_id = _seed_job(conn, status="CLAIMED", lease=future)

    assert worker.requeue_stale_conversation_jobs() == 0
    assert dispatched == []
    with db_session() as conn:
        row = conn.execute("SELECT status FROM conversation_jobs WHERE task_id = ?", (task_id,)).fetchone()
    assert row["status"] == "CLAIMED"


def test_running_task_is_never_requeued(monkeypatch):
    """Even with an expired lease, an in-process task must not double-run."""
    from rapiin import worker
    from rapiin.database import db_session

    dispatched: list[int] = []
    monkeypatch.setattr(worker, "_dispatch_conversation_task", dispatched.append)

    with db_session() as conn:
        task_id = _seed_job(conn, status="CLAIMED", lease="2000-01-01T00:00:00+00:00")

    with worker._RUNNING_LOCK:
        worker._RUNNING_TASKS.add(task_id)
    try:
        assert worker.requeue_stale_conversation_jobs() == 0
        assert dispatched == []
    finally:
        with worker._RUNNING_LOCK:
            worker._RUNNING_TASKS.discard(task_id)


def test_run_task_requeues_on_transient_error(monkeypatch):
    """A dropped connection mid-turn yields REQUEUE instead of a FAILED task."""
    from rapiin import worker
    from rapiin.database import db_session

    with db_session() as conn:
        task_id = _seed_job(conn, status="PENDING", lease=None)

    def boom(*args, **kwargs):
        raise OperationalError("server closed the connection unexpectedly")

    monkeypatch.setattr(worker, "get_task", lambda conn, tid: {"id": tid, "status": "RUNNING"}, raising=False)
    monkeypatch.setattr(worker, "_run_task", boom)
    # Claim then run: the claim flips PENDING -> CLAIMED, boom is transient.
    with worker._RUNNING_LOCK:
        worker._RUNNING_TASKS.discard(task_id)
    worker._claim_and_run(task_id=task_id)
    with db_session() as conn:
        row = conn.execute("SELECT status, error FROM conversation_jobs WHERE task_id = ?", (task_id,)).fetchone()
    assert row["status"] == "PENDING", "transient loss must requeue, not fail"
    assert not row["error"]
