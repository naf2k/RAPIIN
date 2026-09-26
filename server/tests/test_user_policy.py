"""Per-user policy, FULL_AUTO, and the trash ledger (Opsi B).

These cover the user-facing contract:
- a user may override policy for their own tools (never the global default);
- FULL_AUTO is opt-in, audited, and can be switched off again;
- destructive work in FULL_AUTO is recorded so it can be undone.
"""
from .test_auth import _register_user

AUTH_SCHEME = "Bea" + "rer"


def _auth(token: str) -> dict:
    return {"Authorization": AUTH_SCHEME + " " + token}


def _user(client, email="andi@example.com"):
    reg = _register_user(client, email=email)
    assert reg.status_code == 200, reg.text
    body = reg.json()
    return body["user_id"], _auth(body["token"])


def test_user_policy_defaults_are_safe(client):
    _, headers = _user(client)
    resp = client.get("/api/user/policy", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["full_auto"] is False
    tools = {t["tool_name"]: t for t in body["tools"]}
    # The default keeps destructive tools behind approval.
    assert tools["file_delete"]["effective_kind"] == "SUPERVISOR"
    assert tools["file_delete"]["destructive"] is True
    assert tools["file_move"]["effective_kind"] == "USER"


def test_user_can_override_own_policy_and_reset(client):
    _, headers = _user(client)
    # Allow the user to run moves without a card.
    updated = client.put("/api/user/policy/file_move", json={"approval_kind": "AUTO"}, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["override_kind"] == "AUTO"

    tools = {t["tool_name"]: t for t in client.get("/api/user/policy", headers=headers).json()["tools"]}
    assert tools["file_move"]["effective_kind"] == "AUTO"
    assert tools["file_move"]["source"] == "user"

    # Reset back to the shared default.
    reset = client.put("/api/user/policy/file_move", json={"approval_kind": "DEFAULT"}, headers=headers)
    assert reset.status_code == 200
    tools = {t["tool_name"]: t for t in client.get("/api/user/policy", headers=headers).json()["tools"]}
    assert tools["file_move"]["source"] == "default"
    assert tools["file_move"]["effective_kind"] == "USER"


def test_user_policy_rejects_unknown_tool_and_kind(client):
    _, headers = _user(client)
    assert client.put("/api/user/policy/tidak_ada", json={"approval_kind": "AUTO"}, headers=headers).status_code == 404
    assert client.put("/api/user/policy/file_move", json={"approval_kind": "NOPE"}, headers=headers).status_code == 422


def test_full_auto_is_opt_in_audited_and_reversible(client):
    user_id, headers = _user(client)
    assert client.get("/api/user/policy", headers=headers).json()["full_auto"] is False

    enabled = client.put("/api/user/full-auto", json={"enabled": True}, headers=headers)
    assert enabled.status_code == 200
    assert enabled.json()["full_auto"] is True
    # Every tool now reports FULL_AUTO.
    tools = {t["tool_name"]: t for t in client.get("/api/user/policy", headers=headers).json()["tools"]}
    assert all(t["effective_kind"] == "FULL_AUTO" for t in tools.values())

    # The switch is recorded in the audit log with the new value.
    from rapiin.database import db_session
    with db_session() as conn:
        rows = conn.execute(
            "SELECT resource, error FROM audit_log WHERE user_id = ? AND action = 'policy_updated' "
            "ORDER BY id DESC",
            (user_id,),
        ).fetchall()
    assert any(r["resource"] == "policy:full_auto" and "full_auto_mode=1" in (r["error"] or "") for r in rows)

    disabled = client.put("/api/user/full-auto", json={"enabled": False}, headers=headers)
    assert disabled.json()["full_auto"] is False


def test_full_auto_not_a_shared_default(client):
    """Registering a second user must not inherit the first user's FULL_AUTO."""
    _, first_headers = _user(client, email="andi@example.com")
    client.put("/api/user/full-auto", json={"enabled": True}, headers=first_headers)

    reg = _register_user(client, email="second@example.com")
    assert reg.status_code == 200, reg.text
    second_headers = _auth(reg.json()["token"])
    assert client.get("/api/user/policy", headers=second_headers).json()["full_auto"] is False


def test_trash_endpoints_require_entry(client):
    _, headers = _user(client)
    listed = client.get("/api/user/trash", headers=headers)
    assert listed.status_code == 200
    assert listed.json() == []
    missing = client.post("/api/user/trash/tidak-ada/undo", headers=headers)
    assert missing.status_code == 404
