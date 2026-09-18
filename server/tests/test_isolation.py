"""Isolation and permission tests."""
from pathlib import Path

from .test_auth import _register_user


def _login(client, email):
    return client.post(
        "/api/auth/login", json={"email": email, "password": "Password123!"}
    ).json()["token"]


def test_user_cannot_read_other_user_conversation(client):
    _register_user(client, "andi@example.com")
    _register_user(client, "budi@example.com")
    token_a = _login(client, "andi@example.com")
    token_b = _login(client, "budi@example.com")

    conv = client.post(
        "/api/user/conversations",
        json={"title": "Privat A"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    conversation_id = conv.json()["conversation_id"]

    resp = client.get(
        f"/api/user/conversations/{conversation_id}/messages",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 404

    resp = client.get(
        "/api/user/conversations",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert all(c["id"] != conversation_id for c in resp.json())


def test_memory_isolated_per_user(client):
    _register_user(client, "andi@example.com")
    _register_user(client, "budi@example.com")
    token_a = _login(client, "andi@example.com")
    token_b = _login(client, "budi@example.com")

    client.post(
        "/api/user/memory",
        json={"key": "project", "value": "Rahasia A"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    memory_b = client.get("/api/user/memory", headers={"Authorization": f"Bearer {token_b}"}).json()
    assert "project" not in memory_b


def test_approval_engine_supervisor_kind(client):
    """Approval engine: bulk destructive ops require SUPERVISOR approval."""
    from rapiin.approval import create_approval, get_approval
    from rapiin.database import db_session

    with db_session() as conn:
        approval_id = create_approval(
            conn,
            task_id=None,
            user_id=1,
            requested_by="RAPIIN",
            kind="SUPERVISOR",
            action="Bulk delete file",
            scope="Downloads",
            risk="Permanent",
        )
        assert approval_id > 0
        approval = get_approval(conn, approval_id)
        assert approval["status"] == "PENDING"
        assert approval["kind"] == "SUPERVISOR"
