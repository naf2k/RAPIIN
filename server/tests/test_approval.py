"""Approval flow tests."""
from .test_auth import _register_user


def _login(client, email, password="Password123!"):
    return client.post(
        "/api/auth/login", json={"email": email, "password": password}
    ).json()["token"]


def test_user_approval_respond_flow(client):
    reg = _register_user(client)
    user_id = reg.json()["user_id"]
    token = _login(client, "andi@example.com")

    # Create approval directly in the DB for the registered user.
    from rapiin.approval import create_approval, get_approval
    from rapiin.database import db_session

    with db_session() as conn:
        approval_id = create_approval(
            conn,
            task_id=None,
            user_id=user_id,
            requested_by="RAPIIN",
            kind="USER",
            action="Memindahkan file laporan",
            scope="Downloads/laporan.pdf",
            risk="Perubahan file",
        )

    resp = client.post(
        f"/api/user/approvals/{approval_id}/respond",
        json={"decision": "APPROVED"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "APPROVED"

    with db_session() as conn:
        approval = get_approval(conn, approval_id)
        assert approval["status"] == "APPROVED"


def test_supervisor_required_for_supervisor_approval(client):
    user_reg = _register_user(client, "andi@example.com")
    assert user_reg.status_code == 200, user_reg.text
    user_id = user_reg.json()["user_id"]
    user_token = _login(client, "andi@example.com")
    sup_login = client.post(
        "/api/auth/login", json={"email": "supervisor@rapiin.example.com", "password": "Supervisor123!"}
    )
    assert sup_login.status_code == 200, sup_login.text
    sup_token = sup_login.json()["token"]

    from rapiin.approval import create_approval, get_approval
    from rapiin.database import db_session

    with db_session() as conn:
        approval_id = create_approval(
            conn,
            task_id=None,
            user_id=user_id,
            requested_by="RAPIIN",
            kind="SUPERVISOR",
            action="Menghapus 183 file duplikat",
            risk="Penghapusan permanen",
        )

    # Regular user cannot decide a SUPERVISOR approval
    resp = client.post(
        f"/api/user/approvals/{approval_id}/respond",
        json={"decision": "APPROVED"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 403

    # Supervisor can
    resp = client.post(
        f"/api/supervisor/approvals/{approval_id}/respond",
        json={"decision": "APPROVED"},
        headers={"Authorization": f"Bearer {sup_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "APPROVED"


def test_supervisor_approvals_list(client):
    from rapiin.approval import create_approval
    from rapiin.database import db_session

    reg = _register_user(client, "andi@example.com")
    user_id = reg.json()["user_id"]

    with db_session() as conn:
        create_approval(
            conn,
            task_id=None,
            user_id=user_id,
            requested_by="RAPIIN",
            kind="SUPERVISOR",
            action="Bulk rename",
            risk="Perubahan file",
        )

    token = _login(client, "supervisor@rapiin.example.com", "Supervisor123!")
    resp = client.get("/api/supervisor/approvals", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert len(resp.json()) >= 1
