"""User API - conversations, messages, tasks, approvals, memory.

User-scoped endpoints. Authorization is enforced server-side (PRD 7).
"""
from __future__ import annotations

import json
import queue

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..approval import get_approval, pending_approvals_for_user, respond_approval
from ..audit import record_audit
from ..database import utcnow_iso
from ..memory import add_message, get_conversation_messages, get_memory, set_memory
from ..notifications import list_for_user, mark_read, unread_count
from ..tasks import create_task, get_task, list_tasks, update_task
from .deps import get_db, require_user

router = APIRouter(prefix="/api/user", tags=["user"])


class ConversationCreate(BaseModel):
    title: str | None = None


class MessageCreate(BaseModel):
    content: str
    device_id: int | None = None


class ApprovalRespond(BaseModel):
    decision: str  # APPROVED or REJECTED


class MemorySet(BaseModel):
    key: str
    value: str


def _get_user_conversation(conn, user_id: int, conversation_id: int) -> dict:
    row = conn.execute(
        "SELECT * FROM conversations WHERE id = ? AND user_id = ?", (conversation_id, user_id)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Percakapan tidak ditemukan.")
    return dict(row)


def _resolve_online_device(conn, user_id: int, requested_device_id: int | None) -> int | None:
    """Resolve an owned online target without silently misrouting multi-device work."""
    if requested_device_id is not None:
        row = conn.execute(
            "SELECT id, status FROM devices WHERE id = ? AND user_id = ?",
            (requested_device_id, user_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Perangkat tujuan tidak ditemukan.")
        if row["status"] != "ONLINE":
            raise HTTPException(status_code=409, detail="Perangkat tujuan sedang offline.")
        return row["id"]

    rows = conn.execute(
        "SELECT id FROM devices WHERE user_id = ? AND status = 'ONLINE' ORDER BY id DESC LIMIT 2",
        (user_id,),
    ).fetchall()
    if len(rows) > 1:
        raise HTTPException(status_code=409, detail="Pilih perangkat tujuan sebelum mengirim perintah.")
    return rows[0]["id"] if rows else None


@router.post("/conversations")
def create_conversation(body: ConversationCreate, user=Depends(require_user), conn=Depends(get_db)):
    title = body.title or "Percakapan baru"
    now = utcnow_iso()
    cur = conn.execute(
        "INSERT INTO conversations (user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (user["id"], title, now, now),
    )
    record_audit(
        conn,
        actor=user["name"],
        actor_role="USER",
        user_id=user["id"],
        action="conversation_created",
        resource=f"conversation:{cur.lastrowid}",
    )
    return {"conversation_id": cur.lastrowid, "title": title}


@router.get("/conversations")
def list_conversations(user=Depends(require_user), conn=Depends(get_db)):
    rows = conn.execute(
        "SELECT id, title, created_at, updated_at FROM conversations WHERE user_id = ? ORDER BY updated_at DESC LIMIT 50",
        (user["id"],),
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/conversations/{conversation_id}/messages")
def get_messages_route(conversation_id: int, user=Depends(require_user), conn=Depends(get_db)):
    _get_user_conversation(conn, user["id"], conversation_id)
    messages = get_conversation_messages(conn, conversation_id, limit=100)
    return [m for m in messages if m["role"] in {"user", "assistant"}]


@router.post("/conversations/{conversation_id}/messages")
def post_message_route(conversation_id: int, body: MessageCreate, user=Depends(require_user), conn=Depends(get_db)):
    conversation = _get_user_conversation(conn, user["id"], conversation_id)
    if not body.content.strip():
        raise HTTPException(status_code=422, detail="Pesan tidak boleh kosong.")

    device_id = _resolve_online_device(conn, user["id"], body.device_id)

    add_message(conn, conversation_id, "user", body.content)

    task_id = create_task(conn, user_id=user["id"], device_id=device_id, type="conversation")
    update_task(conn, task_id, status="PLANNING")
    record_audit(
        conn,
        actor=user["name"],
        actor_role="USER",
        user_id=user["id"],
        device_id=device_id,
        action="user_message",
        resource=f"conversation:{conversation_id}",
        task_id=task_id,
    )

    history = get_conversation_messages(conn, conversation_id, limit=40)
    memory = get_memory(conn, user["id"])
    if memory:
        history.insert(0, {
            "role": "assistant",
            "content": "Konteks pribadi pengguna (jangan dibagikan): "
                       + "; ".join(f"{k}={v}" for k, v in memory.items()),
        })

    # Commit message/task before spawning the async worker so the worker's own
    # connection sees them, then hand the conversation to the background task
    # queue (PRD sections 15, 23). The HTTP request returns immediately.
    conn.commit()
    from ..worker import spawn_conversation_task

    spawn_conversation_task(
        user_id=user["id"],
        conversation_id=conversation_id,
        task_id=task_id,
        device_id=device_id,
    )
    return {
        "reply": None,
        "task_id": task_id,
        "status": "PROCESSING",
        "message": "BERESIN sedang memproses permintaan Anda.",
    }


@router.get("/tasks")
def user_tasks(user=Depends(require_user), conn=Depends(get_db)):
    return list_tasks(conn, user_id=user["id"], limit=50)


@router.get("/tasks/{task_id}")
def user_task_detail(task_id: int, user=Depends(require_user), conn=Depends(get_db)):
    task = get_task(conn, task_id)
    if not task or task["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Task tidak ditemukan.")
    return task


@router.post("/tasks/{task_id}/cancel")
def user_cancel_task(task_id: int, user=Depends(require_user), conn=Depends(get_db)):
    task = get_task(conn, task_id)
    if not task or task["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Task tidak ditemukan.")
    if task["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
        raise HTTPException(status_code=409, detail="Task sudah selesai.")
    claimed = conn.execute("SELECT id FROM agent_jobs WHERE task_id = ? AND status = 'CLAIMED'", (task_id,)).fetchone()
    if claimed:
        raise HTTPException(status_code=409, detail="Operasi file sedang dieksekusi dan tidak aman dihentikan di tengah proses.")
    conn.execute("UPDATE tasks SET cancel_requested = 1 WHERE id = ?", (task_id,))
    conn.execute("UPDATE agent_jobs SET status = 'FAILED', error = 'Dibatalkan pengguna', finished_at = ? WHERE task_id = ? AND status = 'PENDING'", (utcnow_iso(), task_id))
    conn.execute("UPDATE approvals SET status = 'REJECTED', decided_by = ?, decided_at = ? WHERE task_id = ? AND status = 'PENDING'", (user["id"], utcnow_iso(), task_id))
    if task["status"] in {"PENDING", "WAITING_APPROVAL"}:
        update_task(conn, task_id, status="CANCELLED", completed=True)
    record_audit(conn, actor=user["name"], actor_role="USER", user_id=user["id"], device_id=task["device_id"], action="task_cancel_requested", resource=f"task:{task_id}", task_id=task_id)
    return {"task_id": task_id, "status": "CANCELLED" if task["status"] in {"PENDING", "WAITING_APPROVAL"} else "CANCELLING"}


@router.get("/tasks/{task_id}/events")
def user_task_events(task_id: int, user=Depends(require_user), conn=Depends(get_db)):
    """Stream task progress and AI text deltas; bearer auth works with fetch()."""
    task = get_task(conn, task_id)
    if not task or task["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Task tidak ditemukan.")

    from ..events import subscribe, unsubscribe
    subscriber = subscribe(task_id)

    def stream():
        try:
            yield "data: " + json.dumps({
                "type": "progress", "task_id": task_id,
                "status": task["status"], "progress": task["progress"],
                "processed_count": task.get("processed_count", 0),
                "total_count": task.get("total_count", 0),
            }) + "\n\n"
            if task["status"] in {"COMPLETED", "FAILED", "CANCELLED", "WAITING_APPROVAL"}:
                return
            while True:
                try:
                    event = subscriber.get(timeout=15)
                    yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
                    if event.get("status") in {"COMPLETED", "FAILED", "CANCELLED", "WAITING_APPROVAL"}:
                        break
                except queue.Empty:
                    yield ": keep-alive\n\n"
        finally:
            unsubscribe(task_id, subscriber)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.get("/approvals")
def user_approvals(user=Depends(require_user), conn=Depends(get_db)):
    return pending_approvals_for_user(conn, user["id"])


@router.post("/approvals/{approval_id}/respond")
def user_approval_respond(approval_id: int, body: ApprovalRespond, user=Depends(require_user), conn=Depends(get_db)):
    approval = get_approval(conn, approval_id)
    if not approval or approval["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Approval tidak ditemukan.")
    if approval["kind"] == "SUPERVISOR":
        raise HTTPException(status_code=403, detail="Approval ini harus diputuskan supervisor.")
    try:
        updated = respond_approval(
            conn,
            approval_id,
            decision=body.decision,
            decided_by_id=user["id"],
            decided_by_name=user["name"],
            decided_by_role="USER",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return updated


@router.get("/devices")
def user_devices(user=Depends(require_user), conn=Depends(get_db)):
    from ..devices import device_status_view
    rows = conn.execute(
        "SELECT id, device_name, os, agent_version, status, last_heartbeat_at, capabilities FROM devices WHERE user_id = ?",
        (user["id"],),
    ).fetchall()
    return [device_status_view(conn, r) for r in rows]


@router.get("/memory")
def user_memory(user=Depends(require_user), conn=Depends(get_db)):
    return get_memory(conn, user["id"])


@router.post("/memory")
def set_user_memory(body: MemorySet, user=Depends(require_user), conn=Depends(get_db)):
    from ..redaction import SENSITIVE_KEY, redact_text
    if SENSITIVE_KEY.search(body.key):
        raise HTTPException(status_code=422, detail="Password, token, API key, dan credential tidak boleh disimpan sebagai memory.")
    cleaned = redact_text(body.value)
    if cleaned != body.value:
        raise HTTPException(status_code=422, detail="Nilai memory terdeteksi mengandung credential dan tidak disimpan.")
    set_memory(conn, user["id"], "private", body.key, cleaned)
    return {"key": body.key, "stored": True}


@router.get("/notifications")
def user_notifications(user=Depends(require_user), conn=Depends(get_db)):
    return list_for_user(conn, user["id"], "USER")


@router.get("/notifications/unread-count")
def user_notifications_unread(user=Depends(require_user), conn=Depends(get_db)):
    return {"count": unread_count(conn, user["id"], "USER")}


@router.post("/notifications/{notification_id}/read")
def user_notification_read(notification_id: int, user=Depends(require_user), conn=Depends(get_db)):
    if not mark_read(conn, notification_id, user["id"]):
        raise HTTPException(status_code=404, detail="Notifikasi tidak ditemukan.")
    return {"status": "ok"}


class ProfileUpdate(BaseModel):
    name: str | None = None
    password: str | None = None


@router.get("/profile")
def user_profile(user=Depends(require_user)):
    return {"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"]}


@router.patch("/profile")
def user_update_profile(body: ProfileUpdate, conn=Depends(get_db), user=Depends(require_user)):
    from ..security import hash_password, password_is_strong

    if body.name and body.name.strip():
        conn.execute("UPDATE users SET name = ? WHERE id = ?", (body.name.strip(), user["id"]))
    if body.password:
        if not password_is_strong(body.password):
            raise HTTPException(status_code=422, detail="Kata sandi minimal 12 karakter dan harus memuat huruf besar, huruf kecil, serta angka.")
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(body.password), user["id"]))
        conn.execute("DELETE FROM auth_tokens WHERE user_id = ?", (user["id"],))
    record_audit(
        conn,
        actor=user["name"],
        actor_role="USER",
        user_id=user["id"],
        action="profile_updated",
        resource=f"user:{user['id']}",
    )
    return {"status": "ok"}


class UserSettingPut(BaseModel):
    key: str
    value: str


@router.get("/settings")
def user_settings_get(user=Depends(require_user), conn=Depends(get_db)):
    rows = conn.execute("SELECT key, value FROM user_settings WHERE user_id = ?", (user["id"],)).fetchall()
    return {r["key"]: r["value"] for r in rows}


@router.put("/settings")
def user_settings_put(body: UserSettingPut, user=Depends(require_user), conn=Depends(get_db)):
    conn.execute(
        """
        INSERT INTO user_settings (user_id, key, value, updated_at) VALUES (?, ?, ?, ?)
        ON CONFLICT (user_id, key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (user["id"], body.key, body.value, utcnow_iso()),
    )
    return {"key": body.key, "value": body.value, "stored": True}


class RecommendationApply(BaseModel):
    source_task_id: int
    recommendation_id: str | int


@router.post("/recommendations/apply")
def apply_recommendation(body: RecommendationApply, user=Depends(require_user), conn=Depends(get_db)):
    """Turn a structured recommendation into an approval-gated action.

    The action is stored on the approval (tool_name/tool_args); when the user
    approves, the engine executes it (on the device agent when online) and
    verifies the result.
    """
    from ..approval import create_approval

    source_task = get_task(conn, body.source_task_id)
    if not source_task or source_task["user_id"] != user["id"] or source_task["status"] != "COMPLETED":
        raise HTTPException(status_code=404, detail="Snapshot rekomendasi tidak ditemukan.")
    try:
        result = json.loads(source_task.get("result_json") or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=409, detail="Snapshot rekomendasi rusak.") from exc
    recommendation = None
    directory = None
    for event in result.get("tool_events", []):
        event_result = event.get("result") or {}
        if event.get("tool") != "folder_organizer":
            continue
        for candidate in event_result.get("recommendations", []):
            if str(candidate.get("id")) == str(body.recommendation_id):
                recommendation = candidate
                directory = event_result.get("directory")
                break
    if not recommendation or not directory:
        raise HTTPException(status_code=404, detail="Rekomendasi tidak ada pada snapshot task tersebut.")
    apply = recommendation.get("apply") or {}
    tool_name = apply.get("tool_name")
    tool_args = apply.get("tool_args")
    if tool_name not in {"file_delete", "batch_executor"} or not isinstance(tool_args, dict):
        raise HTTPException(status_code=422, detail="Rencana rekomendasi tidak valid.")

    kind = recommendation.get("kind", "")
    title = {
        "delete_duplicates": "Hapus file duplikat persis",
        "create_folders_by_type": "Buat folder berdasarkan jenis file",
        "group_by_year": "Kelompokkan file berdasarkan tahun",
    }.get(kind, "Terapkan rekomendasi")

    # A recommendation contains paths from the device that produced its snapshot.
    # Running it elsewhere could mutate unrelated files with coincidentally equal paths.
    device_id = source_task.get("device_id")
    if device_id is None:
        raise HTTPException(status_code=409, detail="Snapshot tidak memiliki perangkat sumber.")
    _resolve_online_device(conn, user["id"], device_id)

    task_id = create_task(conn, user_id=user["id"], device_id=device_id, type="organize")
    approval_id = create_approval(
        conn,
        task_id=task_id,
        user_id=user["id"],
        requested_by="BERESIN",
        kind="USER",
        action=f"{title} ({directory})",
        scope=str(directory),
        risk="Penghapusan permanen" if tool_name in {"file_delete", "bulk_delete"} else "Pemindahan file",
        tool_name=tool_name,
        tool_args=tool_args,
    )
    count = len(tool_args.get("paths") or tool_args.get("moves") or [])
    record_audit(
        conn,
        actor=user["name"],
        actor_role="USER",
        user_id=user["id"],
        device_id=device_id,
        action="recommendation_apply_requested",
        resource=f"recommendation:{kind}",
        task_id=task_id,
    )
    return {
        "approval_id": approval_id,
        "task_id": task_id,
        "status": "WAITING_APPROVAL",
        "action": title,
        "tool": tool_name,
        "file_count": count,
    }
