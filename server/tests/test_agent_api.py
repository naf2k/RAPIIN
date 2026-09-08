"""Tests for the Desktop Agent job queue API."""
import json

from beresin.security import hash_token


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

    from beresin.agent_jobs import enqueue_job
    from beresin.database import db_session

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
    from beresin.database import db_session
    with db_session() as conn:
        stored = conn.execute("SELECT workspace_root FROM devices WHERE id = ?", (device_id,)).fetchone()
    assert stored["workspace_root"] == "/Users/example/Downloads"


def test_agent_result_updates_task(client):
    """Completing a job marks the owning task COMPLETED."""
    device_key, device_id = _register_user_with_key(client, "agent3@example.com")

    from beresin.agent_jobs import enqueue_job
    from beresin.database import db_session
    from beresin.tasks import create_task, get_task

    with db_session() as conn:
        user_id = conn.execute("SELECT id FROM users WHERE email = 'agent3@example.com'").fetchone()["id"]
        task_id = create_task(conn, user_id=user_id, device_id=device_id, type="conversation")
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
    assert task["status"] == "COMPLETED"
