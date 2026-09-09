"""Desktop agent API - used by the installed BERESIN Desktop Agent.

Authentication is the per-device secret (device_key) returned at device
registration. This keeps the agent working even when the employee is not
interacting with the web UI.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..agent_jobs import claim_next_job, finish_job, renew_job_lease
from ..audit import record_audit
from ..database import utcnow_iso
from ..devices import get_device_by_key_hash, heartbeat as do_heartbeat
from ..tasks import get_task, update_task
from .deps import get_db

router = APIRouter(prefix="/api/agent", tags=["agent"])


class PollRequest(BaseModel):
    device_id: int
    device_key: str
    workspace_root: str | None = None
    allowed_roots: list[str] | None = None


class ResultRequest(BaseModel):
    job_id: int
    device_id: int
    device_key: str
    status: str  # SUCCEEDED or FAILED
    result: dict | None = None
    error: str | None = None


class LeaseRenewRequest(BaseModel):
    job_id: int
    device_id: int
    device_key: str


def _authorize_device(conn, device_id: int, device_key: str) -> dict:
    from ..devices import _hash_device_key

    device = get_device_by_key_hash(conn, _hash_device_key(device_key))
    if not device or device["id"] != device_id:
        raise HTTPException(status_code=403, detail="Kredensial perangkat tidak valid.")
    return device


@router.post("/poll")
def poll(body: PollRequest, conn=Depends(get_db)):
    """Claim the next pending job for this device, or return empty."""
    device = _authorize_device(conn, body.device_id, body.device_key)
    if body.workspace_root and body.workspace_root != device.get("workspace_root"):
        conn.execute(
            "UPDATE devices SET workspace_root = ? WHERE id = ?",
            (body.workspace_root, device["id"]),
        )
    encoded_roots = json.dumps(body.allowed_roots) if body.allowed_roots else None
    if encoded_roots and encoded_roots != device.get("allowed_roots"):
        conn.execute("UPDATE devices SET allowed_roots = ? WHERE id = ?", (encoded_roots, device["id"]))
    do_heartbeat(conn, body.device_key)
    job = claim_next_job(conn, device_id=device["id"], claimed_by_key_hash=device["device_key_hash"])
    setting = conn.execute(
        "SELECT value FROM user_settings WHERE user_id = ? AND key = 'startup_mode'", (device["user_id"],)
    ).fetchone()
    settings_payload = {"startup_mode": setting["value"] if setting else None}
    if not job:
        return {"job": None, "settings": settings_payload}
    return {
        "settings": settings_payload,
        "job": {
            "id": job["id"],
            "task_id": job["task_id"],
            "kind": job["kind"],
            "payload": json.loads(job["payload"] or "{}"),
        }
    }


@router.post("/result")
def result(body: ResultRequest, conn=Depends(get_db)):
    """Report the outcome of a claimed job."""
    device = _authorize_device(conn, body.device_id, body.device_key)
    do_heartbeat(conn, body.device_key)
    job = finish_job(
        conn,
        job_id=body.job_id,
        device_id=device["id"],
        claimed_by_key_hash=device["device_key_hash"],
        status=body.status,
        result=body.result,
        error=body.error,
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan atau bukan milik perangkat ini.")

    # Propagate the outcome to the owning task when present.
    if job["task_id"]:
        task = get_task(conn, job["task_id"])
        if task and task["status"] in {"RUNNING", "WAITING_APPROVAL", "PENDING", "PLANNING"}:
            if body.status == "SUCCEEDED":
                tool_result = (body.result or {}).get("tool_result", body.result or {})
                failed = int(tool_result.get("failed_count", 0) or 0) if isinstance(tool_result, dict) else 0
                result_status = tool_result.get("status") if isinstance(tool_result, dict) else None
                if result_status != "OK" or failed:
                    update_task(
                        conn, task["id"], status="FAILED", completed=True, result=body.result,
                        error=tool_result.get("message") or f"{failed} item gagal atau tidak terverifikasi.",
                    )
                else:
                    processed = tool_result.get("verified_count") or tool_result.get("file_count") or 0
                    total = tool_result.get("planned_count") or tool_result.get("file_count") or processed
                    conversation_job = conn.execute(
                        "SELECT 1 FROM conversation_jobs WHERE task_id = ? AND status = 'CLAIMED'",
                        (task["id"],),
                    ).fetchone()
                    if conversation_job and task.get("approval_status") != "APPROVED":
                        # The worker still needs to persist the model's final
                        # answer after receiving this device tool result.
                        update_task(conn, task["id"], status="RUNNING", progress=95, processed_count=processed, total_count=total, result=body.result)
                    else:
                        update_task(conn, task["id"], status="COMPLETED", progress=100, processed_count=processed, total_count=total, completed=True, result=body.result)
            else:
                update_task(conn, task["id"], status="FAILED", error=body.error or "Job perangkat gagal.", completed=True)
    return {"job_id": job["id"], "status": job["status"]}


@router.post("/lease/renew")
def renew_lease(body: LeaseRenewRequest, conn=Depends(get_db)):
    device = _authorize_device(conn, body.device_id, body.device_key)
    do_heartbeat(conn, body.device_key)
    if not renew_job_lease(conn, job_id=body.job_id, device_id=device["id"], claimed_by_key_hash=device["device_key_hash"]):
        raise HTTPException(status_code=409, detail="Job tidak sedang dimiliki perangkat ini.")
    return {"job_id": body.job_id, "status": "CLAIMED", "lease_renewed": True}
