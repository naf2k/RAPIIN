"""Tests for the Desktop Agent job queue API."""
import json


def _register_user_with_key(client, email):
    resp = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "name": "Agent User",
            "password": "Password123!",
            "device_name": "PC-AGENT-1",
            "os": "Windows 11",
            "agent_version": "1.0.0",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return body["device"]["device_key"], body["device"]["id"]


def test_agent_poll_and_result_flow(client):
    """A desktop agent claims and completes a queued job."""
    device_key, device_id = _register_user_with_key(client, "agent1@example.com")

    from rapiin.agent_jobs import enqueue_job
    from rapiin.database import db_session

    with db_session() as conn:
        user_id = conn.execute("SELECT id FROM users WHERE email = 'agent1@example.com'").fetchone()["id"]
        enqueue_job(
            conn,
            task_id=None,
            device_id=device_id,
            user_id=user_id,
            kind="filesystem_scanner",
            payload={"tool": "filesystem_scanner", "arguments": {"path": "."}},
        )

    # Agent polls and claims the job
    poll = client.post(
        "/api/agent/poll",
        json={"device_id": device_id, "device_key": device_key},
    )
    assert poll.status_code == 200, poll.text
    job = poll.json()["job"]
    assert job is not None
    assert job["kind"] == "filesystem_scanner"

    # Agent reports success
    report = client.post(
        "/api/agent/result",
        json={
            "job_id": job["id"],
            "device_id": device_id,
            "device_key": device_key,
            "status": "SUCCEEDED",
            "result": {"tool_result": {"status": "OK", "file_count": 3}},
        },
    )
    assert report.status_code == 200, report.text
    assert report.json()["status"] == "SUCCEEDED"

    # Second poll returns nothing (queue drained)
    poll2 = client.post(
        "/api/agent/poll",
        json={"device_id": device_id, "device_key": device_key},
    )
    assert poll2.json()["job"] is None


def test_agent_rejects_wrong_key(client):
    """A device key that does not match cannot poll jobs."""
    _, device_id = _register_user_with_key(client, "agent2@example.com")
    poll = client.post(
        "/api/agent/poll",
        json={"device_id": device_id, "device_key": "wrong-key"},
    )
    assert poll.status_code == 403


def test_agent_poll_synchronizes_workspace_root(client):
    device_key, device_id = _register_user_with_key(client, "agent-workspace@example.com")
    response = client.post(
        "/api/agent/poll",
        json={
            "device_id": device_id,
            "device_key": device_key,
            "workspace_root": "/Users/example/Downloads",
        },
    )
    assert response.status_code == 200, response.text
    from rapiin.database import db_session
    with db_session() as conn:
        stored = conn.execute("SELECT workspace_root FROM devices WHERE id = ?", (device_id,)).fetchone()
    assert stored["workspace_root"] == "/Users/example/Downloads"


def test_agent_poll_synchronizes_allowed_roots(client):
    device_key, device_id = _register_user_with_key(client, "agent-multi-root@example.com")
    response = client.post(
        "/api/agent/poll",
        json={
            "device_id": device_id,
            "device_key": device_key,
            "workspace_root": "/Users/example/Downloads",
            "allowed_roots": ["/Users/example/Downloads", "/Users/example/Documents"],
        },
    )
    assert response.status_code == 200
    from rapiin.database import db_session
    with db_session() as conn:
        stored = conn.execute("SELECT allowed_roots FROM devices WHERE id = ?", (device_id,)).fetchone()
    assert json.loads(stored["allowed_roots"]) == ["/Users/example/Downloads", "/Users/example/Documents"]


def test_agent_result_keeps_conversation_running_until_final_answer(client):
    """A tool result is not terminal until the AI loop stores its answer."""
    device_key, device_id = _register_user_with_key(client, "agent3@example.com")

    from rapiin.agent_jobs import enqueue_job
    from rapiin.database import db_session, utcnow_iso
    from rapiin.tasks import create_task, get_task

    with db_session() as conn:
        user_id = conn.execute("SELECT id FROM users WHERE email = 'agent3@example.com'").fetchone()["id"]
        task_id = create_task(conn, user_id=user_id, device_id=device_id, type="conversation")
        conversation_id = conn.execute(
            "INSERT INTO conversations(user_id, title, created_at, updated_at) VALUES (?, 'active', ?, ?)",
            (user_id, utcnow_iso(), utcnow_iso()),
        ).lastrowid
        conn.execute(
            "INSERT INTO conversation_jobs(task_id, user_id, conversation_id, device_id, status, created_at) VALUES (?, ?, ?, ?, 'CLAIMED', ?)",
            (task_id, user_id, conversation_id, device_id, utcnow_iso()),
        )
        job_id = enqueue_job(
            conn,
            task_id=task_id,
            device_id=device_id,
            user_id=user_id,
            kind="file_search",
            payload={"tool": "file_search", "arguments": {"query": "x"}},
        )

    poll = client.post(
        "/api/agent/poll",
        json={"device_id": device_id, "device_key": device_key},
    ).json()
    assert poll["job"]["id"] == job_id

    client.post(
        "/api/agent/result",
        json={
            "job_id": job_id,
            "device_id": device_id,
            "device_key": device_key,
            "status": "SUCCEEDED",
            "result": {"tool_result": {"status": "OK", "count": 0}},
        },
    )
    with db_session() as conn:
        task = get_task(conn, task_id)
    assert task["status"] == "RUNNING"
    assert task["progress"] == 95


def test_agent_failed_job_keeps_conversation_running(client):
    """A failed device job must not flash FAILED while the worker still owns it.

    The agent loop turns the tool error into the user's answer, so the task has
    to stay RUNNING until the worker publishes its final response. Otherwise the
    UI shows an error with no answer and the failure lingers on a later
    COMPLETED (seen when an agent rejects a protected path such as /Library).
    """
    device_key, device_id = _register_user_with_key(client, "agent4@example.com")

    from rapiin.agent_jobs import enqueue_job
    from rapiin.database import db_session, utcnow_iso
    from rapiin.tasks import create_task, get_task

    with db_session() as conn:
        user_id = conn.execute("SELECT id FROM users WHERE email = 'agent4@example.com'").fetchone()["id"]
        task_id = create_task(conn, user_id=user_id, device_id=device_id, type="conversation")
        conversation_id = conn.execute(
            "INSERT INTO conversations(user_id, title, created_at, updated_at) VALUES (?, 'active', ?, ?)",
            (user_id, utcnow_iso(), utcnow_iso()),
        ).lastrowid
        conn.execute(
            "INSERT INTO conversation_jobs(task_id, user_id, conversation_id, device_id, status, created_at) VALUES (?, ?, ?, ?, 'CLAIMED', ?)",
            (task_id, user_id, conversation_id, device_id, utcnow_iso()),
        )
        job_id = enqueue_job(
            conn,
            task_id=task_id,
            device_id=device_id,
            user_id=user_id,
            kind="filesystem_scanner",
            payload={"tool": "filesystem_scanner", "arguments": {"path": "/Users/example/Library"}},
        )

    poll = client.post(
        "/api/agent/poll",
        json={"device_id": device_id, "device_key": device_key},
    ).json()
    assert poll["job"]["id"] == job_id

    report = client.post(
        "/api/agent/result",
        json={
            "job_id": job_id,
            "device_id": device_id,
            "device_key": device_key,
            "status": "FAILED",
            "error": "Folder sistem tidak dapat diakses RAPIIN: /Users/example/Library",
        },
    )
    assert report.status_code == 200, report.text

    with db_session() as conn:
        task = get_task(conn, task_id)
    assert task["status"] == "RUNNING"
    assert task["progress"] == 95
    assert not task.get("error"), "worker still owns the turn; no error may be latched"


def test_agent_failed_job_marks_task_when_unowned(client):
    """With no owning conversation job, a failed device job does fail the task."""
    device_key, device_id = _register_user_with_key(client, "agent5@example.com")

    from rapiin.agent_jobs import enqueue_job
    from rapiin.database import db_session
    from rapiin.tasks import create_task, get_task

    with db_session() as conn:
        user_id = conn.execute("SELECT id FROM users WHERE email = 'agent5@example.com'").fetchone()["id"]
        task_id = create_task(conn, user_id=user_id, device_id=device_id, type="conversation")
        job_id = enqueue_job(
            conn,
            task_id=task_id,
            device_id=device_id,
            user_id=user_id,
            kind="filesystem_scanner",
            payload={"tool": "filesystem_scanner", "arguments": {"path": "/Users/example/Library"}},
        )

    client.post(
        "/api/agent/poll",
        json={"device_id": device_id, "device_key": device_key},
    )
    client.post(
        "/api/agent/result",
        json={
            "job_id": job_id,
            "device_id": device_id,
            "device_key": device_key,
            "status": "FAILED",
            "error": "Job perangkat gagal.",
        },
    )

    with db_session() as conn:
        task = get_task(conn, task_id)
    assert task["status"] == "FAILED"
    assert task.get("error")
