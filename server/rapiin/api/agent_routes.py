"""Desktop agent API - used by the installed RAPIIN Desktop Agent.

Authentication is the per-device secret (device_key) returned at device
registration. This keeps the agent working even when the employee is not
interacting with the web UI.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..agent_jobs import claim_next_job, finish_job, renew_job_lease
from ..devices import get_device_by_key_hash
from ..devices import heartbeat as do_heartbeat
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
    from ..ops_incidents import operations_frozen
    if operations_frozen(conn):
        return {"job": None, "settings": {"startup_mode": None}, "operations_paused": True}
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
                    # A device tool can report a sub-status ERROR while the
                    # enclosing conversation turn is still running: the worker
                    # owns that task and will roll up the final outcome. Only
                    # fail the task here when nothing else still owns it,
                    # otherwise a transient tool hiccup would mark a turn
                    # FAILED and leave the error behind on a later COMPLETED.
                    still_owned = conn.execute(
                        "SELECT 1 FROM conversation_jobs WHERE task_id = ? AND status = 'CLAIMED'",
                        (task["id"],),
                    ).fetchone()
                    if still_owned:
                        update_task(conn, task["id"], status="RUNNING", progress=95, result=body.result)
                    else:
                        update_task(
                            conn, task["id"], status="FAILED", completed=True, result=body.result,
                            error=tool_result.get("message") or f"{failed} item gagal atau tidak terverifikasi.",
                        )
                        _announce_approval_outcome(
                            conn, task["id"], job, tool_result, success=False,
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
                        update_task(conn, task["id"], status="COMPLETED", progress=100, processed_count=processed, total_count=total, completed=True, result=body.result, error="")
                        _announce_approval_outcome(conn, task["id"], job, tool_result, success=True)
            else:
                # A failed device job is not necessarily a failed turn: the
                # worker is still running the Hermes loop and will turn this
                # tool error into a user-visible explanation. Marking the task
                # FAILED here would flash an error in the UI with no answer and
                # leave a stale failure behind when the worker later completes
                # the turn. Only fail the task when nothing else owns it.
                still_owned = conn.execute(
                    "SELECT 1 FROM conversation_jobs WHERE task_id = ? AND status = 'CLAIMED'",
                    (task["id"],),
                ).fetchone()
                if still_owned:
                    update_task(conn, task["id"], status="RUNNING", progress=95, result=body.result)
                else:
                    update_task(conn, task["id"], status="FAILED", error=body.error or "Job perangkat gagal.", completed=True)
                    _announce_approval_outcome(
                        conn, task["id"], job, body.result or {}, success=False,
                        error=body.error or "Job perangkat gagal.",
                    )
    return {"job_id": job["id"], "status": job["status"]}


def _announce_approval_outcome(conn, task_id: int, job: dict, tool_result: dict, *, success: bool, error: str | None = None) -> None:
    """Post the outcome of an approved action back into its conversation.

    An approved mutation runs as a device job, and by then the Hermes worker
    has already finished; nothing is left to write the model's answer. Without
    this the chat keeps showing "menunggu persetujuan" even after the file was
    changed. Only approval-driven jobs are announced, and only once, because
    the caller reaches this point on the single terminal transition.
    """
    if not str(job.get("idempotency_key") or "").startswith("approval:"):
        return
    row = conn.execute(
        "SELECT conversation_id FROM conversation_jobs WHERE task_id = ? ORDER BY id DESC LIMIT 1",
        (task_id,),
    ).fetchone()
    if not row or not row["conversation_id"]:
        return
    from ..memory import add_message

    version = job.get("kind") or "tindakan"
    if success:
        verified = int(tool_result.get("verified_count") or tool_result.get("executed_count") or 0)
        planned = int(tool_result.get("planned_count") or verified)
        if verified and planned:
            text = f"Persetujuan diterima. {version} sudah dijalankan ({verified}/{planned} item berhasil)."
        else:
            text = f"Persetujuan diterima. {version} sudah dijalankan di perangkat Anda."
    else:
        text = f"Tindakan yang Anda setujui gagal dijalankan: {error or 'tidak ada detail.'}"
    add_message(conn, row["conversation_id"], "assistant", text)


@router.post("/lease/renew")
def renew_lease(body: LeaseRenewRequest, conn=Depends(get_db)):
    device = _authorize_device(conn, body.device_id, body.device_key)
    do_heartbeat(conn, body.device_key)
    if not renew_job_lease(conn, job_id=body.job_id, device_id=device["id"], claimed_by_key_hash=device["device_key_hash"]):
        raise HTTPException(status_code=409, detail="Job tidak sedang dimiliki perangkat ini.")
    return {"job_id": body.job_id, "status": "CLAIMED", "lease_renewed": True}
