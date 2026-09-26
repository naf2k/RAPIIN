"""Supervisor API - monitoring and approval center.

Authorization is strictly SUPERVISOR (PRD 7, 20, 21).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from ..agent.core import HermesCore
from ..ai.provider import get_provider
from ..approval import all_pending_approvals, get_approval, respond_approval
from ..audit import record_audit
from ..supervisor import (
    build_monitoring_context,
    employee_detail,
    employees,
    overview,
)
from ..tasks import get_task, list_task_activities, list_tasks
from .deps import get_db, require_supervisor

router = APIRouter(prefix="/api/supervisor", tags=["supervisor"])


class ApprovalRespond(BaseModel):
    decision: str


class ChatRequest(BaseModel):
    message: str


class PolicyUpdate(BaseModel):
    approval_kind: str
    bulk_threshold: int = 20


@router.get("/overview")
def supervisor_overview(conn=Depends(get_db), user=Depends(require_supervisor)):
    return overview(conn)


@router.get("/metrics")
def supervisor_metrics(conn=Depends(get_db), user=Depends(require_supervisor)):
    from ..metrics import compute_metrics

    return compute_metrics(conn)


@router.get("/policies")
def supervisor_policies(conn=Depends(get_db), user=Depends(require_supervisor)):
    from ..permissions import AUTO_ACTIONS, SUPERVISOR_APPROVAL_ACTIONS, USER_APPROVAL_ACTIONS
    tools = sorted(AUTO_ACTIONS | USER_APPROVAL_ACTIONS | SUPERVISOR_APPROVAL_ACTIONS)
    configured = {r["tool_name"]: dict(r) for r in conn.execute("SELECT * FROM action_policies").fetchall()}
    result = []
    for tool in tools:
        default = "AUTO" if tool in AUTO_ACTIONS else "SUPERVISOR" if tool in SUPERVISOR_APPROVAL_ACTIONS else "USER"
        result.append(configured.get(tool) or {"tool_name": tool, "approval_kind": default, "bulk_threshold": 20})
    return result


@router.put("/policies/{tool_name}")
def supervisor_update_policy(tool_name: str, body: PolicyUpdate, conn=Depends(get_db), user=Depends(require_supervisor)):
    from ..database import utcnow_iso
    from ..permissions import AUTO_ACTIONS, SUPERVISOR_APPROVAL_ACTIONS, USER_APPROVAL_ACTIONS
    known = AUTO_ACTIONS | USER_APPROVAL_ACTIONS | SUPERVISOR_APPROVAL_ACTIONS
    if tool_name not in known:
        raise HTTPException(status_code=404, detail="Tool policy tidak dikenal.")
    kind = body.approval_kind.upper()
    if kind not in {"AUTO", "USER", "SUPERVISOR"}:
        raise HTTPException(status_code=422, detail="Approval kind tidak valid.")
    if tool_name in {"file_delete", "bulk_delete", "batch_executor"} and kind == "AUTO":
        raise HTTPException(status_code=422, detail="Operasi destruktif tidak boleh otomatis.")
    threshold = max(1, min(body.bulk_threshold, 10000))
    conn.execute(
        """INSERT INTO action_policies (tool_name, approval_kind, bulk_threshold, updated_by, updated_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(tool_name) DO UPDATE SET approval_kind=excluded.approval_kind,
           bulk_threshold=excluded.bulk_threshold, updated_by=excluded.updated_by, updated_at=excluded.updated_at""",
        (tool_name, kind, threshold, user["id"], utcnow_iso()),
    )
    record_audit(conn, actor=user["name"], actor_role="SUPERVISOR", user_id=user["id"], action="policy_updated", resource=f"policy:{tool_name}")
    return {"tool_name": tool_name, "approval_kind": kind, "bulk_threshold": threshold}


@router.get("/employees")
def supervisor_employees(q: str | None = None, conn=Depends(get_db), user=Depends(require_supervisor)):
    emps = employees(conn)
    if q:
        needle = q.lower()
        emps = [
            e for e in emps
            if needle in (e.get("name") or "").lower()
            or needle in (e.get("email") or "").lower()
            or needle in (e.get("device_name") or "").lower()
        ]
    return emps


@router.get("/employees/{user_id}")
def supervisor_employee_detail(user_id: int, conn=Depends(get_db), user=Depends(require_supervisor)):
    data = employee_detail(conn, user_id)
    if not data:
        raise HTTPException(status_code=404, detail="Employee tidak ditemukan.")
    return data


@router.get("/tasks")
def supervisor_tasks(status: str | None = None, q: str | None = None, conn=Depends(get_db), user=Depends(require_supervisor)):
    tasks = list_tasks(conn, status=status or None, limit=500)
    if q:
        needle = q.lower()
        tasks = [
            t for t in tasks
            if needle in (t.get("type") or "").lower()
            or needle in str(t.get("user_id") or "")
            or needle in str(t.get("device_id") or "")
            or needle in (t.get("error") or "").lower()
        ]
    return tasks[:200]


@router.get("/tasks/{task_id}")
def supervisor_task_detail(task_id: int, conn=Depends(get_db), user=Depends(require_supervisor)):
    task = get_task(conn, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task tidak ditemukan.")
    task["activity"] = list_task_activities(conn, task_id)
    return task


@router.get("/approvals")
def supervisor_approvals(include_decided: bool = False, conn=Depends(get_db), user=Depends(require_supervisor)):
    return all_pending_approvals(conn, include_decided=include_decided)


@router.post("/approvals/{approval_id}/respond")
def supervisor_approval_respond(approval_id: int, body: ApprovalRespond, conn=Depends(get_db), user=Depends(require_supervisor)):
    approval = get_approval(conn, approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval tidak ditemukan.")
    try:
        updated = respond_approval(
            conn,
            approval_id,
            decision=body.decision,
            decided_by_id=user["id"],
            decided_by_name=user["name"],
            decided_by_role="SUPERVISOR",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return updated


@router.get("/activity")
def supervisor_activity(conn=Depends(get_db), user=Depends(require_supervisor)):
    rows = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 100").fetchall()
    return [dict(r) for r in rows]


@router.post("/chat")
def supervisor_chat(body: ChatRequest, conn=Depends(get_db), user=Depends(require_supervisor)):
    if not body.message.strip():
        raise HTTPException(status_code=422, detail="Pesan tidak boleh kosong.")
    context = build_monitoring_context(conn)
    core = HermesCore(get_provider())
    reply = core.run_supervisor_question(
        messages=[
            {"role": "system", "content": "Kamu adalah Supervisor Chat RAPIIN."},
            {"role": "user", "content": body.message},
        ],
        monitoring_context=context,
    )
    record_audit(
        conn,
        actor=user["name"],
        actor_role="SUPERVISOR",
        user_id=user["id"],
        action="supervisor_chat",
        resource="supervisor-chat",
    )
    return {"reply": reply}


@router.get("/devices")
def supervisor_devices(conn=Depends(get_db), user=Depends(require_supervisor)):
    from ..devices import device_status_view
    rows = conn.execute(
        """
        SELECT d.id, d.device_name, d.os, d.agent_version, d.status, d.last_heartbeat_at, d.capabilities,
               u.name AS user_name, u.id AS user_id
        FROM devices d JOIN users u ON u.id = d.user_id
        ORDER BY d.id DESC
        """
    ).fetchall()
    return [device_status_view(conn, r) for r in rows]


class ProfileUpdate(BaseModel):
    name: str | None = None
    password: str | None = None


@router.get("/profile")
def supervisor_profile(user=Depends(require_supervisor)):
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
    }


@router.patch("/profile")
def supervisor_update_profile(body: ProfileUpdate, conn=Depends(get_db), user=Depends(require_supervisor)):
    from ..security import hash_password, password_is_strong

    if body.name and body.name.strip():
        conn.execute("UPDATE users SET name = ? WHERE id = ?", (body.name.strip(), user["id"]))
    if body.password and password_is_strong(body.password):
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(body.password), user["id"]),
        )
        conn.execute("DELETE FROM auth_tokens WHERE user_id = ?", (user["id"],))
    elif body.password:
        raise HTTPException(status_code=422, detail="Kata sandi minimal 12 karakter dan harus memuat huruf besar, huruf kecil, serta angka.")
    record_audit(
        conn,
        actor=user["name"],
        actor_role="SUPERVISOR",
        user_id=user["id"],
        action="profile_updated",
        resource=f"user:{user['id']}",
    )
    return {"status": "ok"}


@router.get("/accounts")
def supervisor_accounts(conn=Depends(get_db), user=Depends(require_supervisor)):
    """List supervisor accounts (V1 limit: 2)."""
    rows = conn.execute(
        "SELECT id, name, email, is_active, created_at FROM users WHERE role = 'SUPERVISOR' ORDER BY id"
    ).fetchall()
    return {"count": len(rows), "max": 2, "accounts": [dict(r) for r in rows]}


@router.get("/notifications")
def supervisor_notifications(conn=Depends(get_db), user=Depends(require_supervisor)):
    from ..notifications import list_for_supervisors, unread_count_for_supervisors

    return {
        "items": list_for_supervisors(conn),
        "unread": unread_count_for_supervisors(conn),
    }


@router.post("/notifications/{notification_id}/read")
def supervisor_notification_read(notification_id: int, conn=Depends(get_db), user=Depends(require_supervisor)):
    from ..notifications import mark_read_for_supervisor

    if not mark_read_for_supervisor(conn, notification_id):
        raise HTTPException(status_code=404, detail="Notifikasi tidak ditemukan.")
    return {"status": "ok"}


class EmployeeCreate(BaseModel):
    name: str
    email: EmailStr
    password: str


class EmployeeStateUpdate(BaseModel):
    is_active: bool


@router.post("/accounts")
def supervisor_create_account(body: EmployeeCreate, conn=Depends(get_db), user=Depends(require_supervisor)):
    """Create the optional second supervisor while enforcing the V1 limit."""
    from ..database import utcnow_iso
    from ..security import hash_password, password_is_strong
    count = conn.execute("SELECT COUNT(*) AS n FROM users WHERE role='SUPERVISOR'").fetchone()["n"]
    if count >= 2:
        raise HTTPException(status_code=409, detail="Maksimal dua akun supervisor.")
    email = body.email.strip().lower()
    if not body.name.strip() or not password_is_strong(body.password):
        raise HTTPException(status_code=422, detail="Nama wajib; kata sandi minimal 12 karakter dengan huruf besar, kecil, dan angka.")
    if conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():
        raise HTTPException(status_code=409, detail="Email sudah terdaftar.")
    cur = conn.execute(
        "INSERT INTO users (email,password_hash,name,role,is_active,created_at) VALUES (?,?,?,'SUPERVISOR',1,?)",
        (email, hash_password(body.password), body.name.strip(), utcnow_iso()),
    )
    record_audit(conn, actor=user["name"], actor_role="SUPERVISOR", user_id=cur.lastrowid, action="supervisor_created", resource=f"user:{cur.lastrowid}")
    return {"id": cur.lastrowid, "name": body.name.strip(), "email": email, "role": "SUPERVISOR"}


@router.post("/employees")
def supervisor_create_employee(body: EmployeeCreate, conn=Depends(get_db), user=Depends(require_supervisor)):
    """Create an employee account (PRD: users can be created as needed)."""
    from ..database import utcnow_iso
    from ..security import hash_password, password_is_strong

    email = body.email.strip().lower()
    existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail="Email sudah terdaftar.")
    if not body.name.strip() or not password_is_strong(body.password):
        raise HTTPException(status_code=422, detail="Nama wajib; kata sandi minimal 12 karakter dengan huruf besar, kecil, dan angka.")
    cur = conn.execute(
        "INSERT INTO users (email, password_hash, name, role, is_active, created_at) VALUES (?, ?, ?, 'USER', 1, ?)",
        (email, hash_password(body.password), body.name.strip(), utcnow_iso()),
    )
    record_audit(
        conn,
        actor=user["name"],
        actor_role="SUPERVISOR",
        user_id=cur.lastrowid,
        action="employee_created",
        resource=f"user:{cur.lastrowid}",
    )
    return {"user_id": cur.lastrowid, "email": email, "name": body.name.strip()}


@router.patch("/employees/{user_id}/state")
def supervisor_set_employee_state(user_id: int, body: EmployeeStateUpdate, conn=Depends(get_db), user=Depends(require_supervisor)):
    row = conn.execute("SELECT id FROM users WHERE id = ? AND role = 'USER'", (user_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Employee tidak ditemukan.")
    conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (1 if body.is_active else 0, user_id))
    record_audit(
        conn,
        actor=user["name"],
        actor_role="SUPERVISOR",
        user_id=user_id,
        action="employee_state_changed",
        resource=f"user:{user_id}",
        result="SUCCESS" if body.is_active else "DISABLED",
    )
    return {"status": "ok", "user_id": user_id, "is_active": body.is_active}
