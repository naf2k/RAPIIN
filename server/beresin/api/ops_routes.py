"""Supervisor and monitor endpoints for the Operations Center."""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from ..config import settings
from ..ops_incidents import (
    collect_runtime_signals,
    create_proposal,
    get_incident,
    ingest_signal,
    list_incidents,
    overview,
    respond_approval,
    seed_ops,
    set_freeze,
    set_incident_status,
)
from .deps import get_db, require_supervisor

router = APIRouter(prefix="/api/supervisor/ops", tags=["operations-center"])
internal_router = APIRouter(prefix="/api/internal/ops", tags=["operations-monitor"])


class SignalBody(BaseModel):
    source: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    severity: str
    summary: str = Field(default="", max_length=4000)
    resource: str | None = Field(default=None, max_length=500)
    details: dict = Field(default_factory=dict)


class ProposalBody(BaseModel):
    action_type: str
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=8000)
    risk: str = Field(default="", max_length=2000)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=100)


class ApprovalBody(BaseModel):
    decision: str
    note: str = Field(default="", max_length=4000)
    password: str | None = Field(default=None, min_length=1, max_length=500)


class StatusBody(BaseModel):
    status: str
    note: str = Field(default="", max_length=4000)


class FreezeBody(BaseModel):
    enabled: bool
    reason: str = Field(default="", max_length=2000)


class CodeActionBody(BaseModel):
    approval_id: int


class DeployBody(BaseModel):
    code_change_id: int
    approval_id: int
    environment: str = Field(default="production", pattern="^(staging|production)$")


@router.get("/overview")
def ops_overview(refresh: bool = False, conn=Depends(get_db), user=Depends(require_supervisor)):
    seed_ops(conn)
    if refresh:
        collect_runtime_signals(conn)
    return overview(conn)


@router.get("/agents")
def ops_agents(conn=Depends(get_db), user=Depends(require_supervisor)):
    seed_ops(conn)
    return [dict(r) for r in conn.execute("SELECT * FROM ops_agents ORDER BY id").fetchall()]


@router.get("/usage")
def ops_usage(conn=Depends(get_db), user=Depends(require_supervisor)):
    from datetime import datetime, timezone
    day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    rows = conn.execute(
        """SELECT g.role, COUNT(u.id) runs,
                  SUM(CASE WHEN u.status='SUCCEEDED' THEN 1 ELSE 0 END) succeeded,
                  SUM(CASE WHEN u.status='FAILED' THEN 1 ELSE 0 END) failed,
                  COALESCE(SUM(u.duration_ms),0) duration_ms,
                  COALESCE(SUM(u.prompt_chars),0) prompt_chars,
                  COALESCE(SUM(u.output_chars),0) output_chars,
                  COALESCE(SUM(u.input_tokens),0) input_tokens,
                  COALESCE(SUM(u.output_tokens),0) output_tokens,
                  COALESCE(SUM(u.api_calls),0) api_calls,
                  COALESCE(SUM(u.estimated_cost_usd),0) estimated_cost_usd
           FROM ops_agents g LEFT JOIN ops_agent_usage u ON u.agent_id=g.id
             AND u.created_at >= ?
           GROUP BY g.id,g.role ORDER BY g.id""",
        (day_start,),
    ).fetchall()
    return {
        "daily_limit": settings.ops_agent_daily_run_limit,
        "daily_cost_limit_usd": settings.ops_agent_daily_cost_limit_usd,
        "monthly_cost_limit_usd": settings.ops_agent_monthly_cost_limit_usd,
        "agents": [dict(row) for row in rows],
    }


@router.get("/policies")
def ops_policies(conn=Depends(get_db), user=Depends(require_supervisor)):
    seed_ops(conn)
    return [dict(r) for r in conn.execute("SELECT * FROM ops_policies ORDER BY key").fetchall()]


@router.get("/incidents")
def ops_incidents(status: str | None = None, severity: str | None = None, conn=Depends(get_db), user=Depends(require_supervisor)):
    return list_incidents(conn, status=status, severity=severity)


@router.get("/incidents/{incident_id}")
def ops_incident_detail(incident_id: int, conn=Depends(get_db), user=Depends(require_supervisor)):
    item = get_incident(conn, incident_id)
    if not item:
        raise HTTPException(status_code=404, detail="Insiden tidak ditemukan.")
    return item


@router.post("/incidents/{incident_id}/proposals")
def ops_create_proposal(incident_id: int, body: ProposalBody, conn=Depends(get_db), user=Depends(require_supervisor)):
    try:
        return create_proposal(conn, incident_id, action_type=body.action_type, title=body.title, description=body.description, risk=body.risk, actor=user, idempotency_key=body.idempotency_key)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/incidents/{incident_id}/status")
def ops_status(incident_id: int, body: StatusBody, conn=Depends(get_db), user=Depends(require_supervisor)):
    try:
        return set_incident_status(conn, incident_id, body.status, user, body.note)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/approvals")
def ops_approvals(conn=Depends(get_db), user=Depends(require_supervisor)):
    return [dict(r) for r in conn.execute("SELECT * FROM ops_approvals ORDER BY CASE status WHEN 'PENDING' THEN 0 ELSE 1 END, id DESC LIMIT 200").fetchall()]


@router.post("/approvals/{approval_id}/respond")
def ops_approval_response(approval_id: int, body: ApprovalBody, conn=Depends(get_db), user=Depends(require_supervisor)):
    try:
        if body.decision.upper() == "APPROVED":
            from ..security import verify_password
            stored = conn.execute("SELECT password_hash FROM users WHERE id=?", (user["id"],)).fetchone()
            if not body.password or not stored or not verify_password(body.password, stored["password_hash"]):
                raise HTTPException(status_code=403, detail="Masukkan ulang password supervisor untuk approval berisiko.")
        return respond_approval(conn, approval_id, decision=body.decision, note=body.note, actor=user)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/emergency-pause")
def ops_emergency_pause(body: FreezeBody, conn=Depends(get_db), user=Depends(require_supervisor)):
    return set_freeze(conn, body.enabled, body.reason, user)


@router.get("/notifications")
def ops_notifications(conn=Depends(get_db), user=Depends(require_supervisor)):
    return [dict(r) for r in conn.execute("SELECT * FROM ops_notifications ORDER BY id DESC LIMIT 100").fetchall()]


@router.get("/audit/integrity")
def ops_audit_integrity(conn=Depends(get_db), user=Depends(require_supervisor)):
    from ..audit import verify_audit_chain
    return verify_audit_chain(conn)


@router.get("/audit/export")
def ops_audit_export(limit: int = 1000, conn=Depends(get_db), user=Depends(require_supervisor)):
    from ..audit import verify_audit_chain
    from ..ops_safety import sanitize
    rows = conn.execute(
        "SELECT id,actor,actor_role,action,resource,timestamp,result,approval_id,task_id,previous_hash,event_hash FROM audit_log ORDER BY id DESC LIMIT ?",
        (min(max(limit, 1), 5000),),
    ).fetchall()
    return {"integrity": verify_audit_chain(conn), "events": [sanitize(dict(row)) for row in rows]}


@router.post("/incidents/{incident_id}/agents/dispatch")
def ops_dispatch_agents(incident_id: int, conn=Depends(get_db), user=Depends(require_supervisor)):
    from ..ops_runtime import dispatch_incident
    if not get_incident(conn, incident_id):
        raise HTTPException(status_code=404, detail="Insiden tidak ditemukan.")
    return {"results": dispatch_incident(conn, incident_id)}


@router.post("/incidents/{incident_id}/code/provision")
def ops_provision_code(incident_id: int, body: CodeActionBody, conn=Depends(get_db), user=Depends(require_supervisor)):
    from ..ops_workflows import provision_worktree
    try:
        return provision_worktree(conn, incident_id, body.approval_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/code-changes/{change_id}/run-coder")
def ops_run_coder(change_id: int, conn=Depends(get_db), user=Depends(require_supervisor)):
    from ..ops_workflows import run_coder
    try:
        return run_coder(conn, change_id)
    except (PermissionError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/code-changes/{change_id}/cancel")
def ops_cancel_code(change_id: int, conn=Depends(get_db), user=Depends(require_supervisor)):
    from ..ops_workflows import cancel_code_change
    try:
        return cancel_code_change(conn, change_id, user)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/code-changes/{change_id}/cleanup")
def ops_cleanup_code(change_id: int, conn=Depends(get_db), user=Depends(require_supervisor)):
    from ..ops_workflows import cleanup_code_worktree
    try:
        return cleanup_code_worktree(conn, change_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (PermissionError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/code-changes/{change_id}/checks")
def ops_run_checks(change_id: int, conn=Depends(get_db), user=Depends(require_supervisor)):
    from ..ops_workflows import run_checks
    try:
        return {"checks": run_checks(conn, change_id)}
    except (LookupError, PermissionError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/code-changes/{change_id}/pull-request")
def ops_pull_request(change_id: int, conn=Depends(get_db), user=Depends(require_supervisor)):
    from ..ops_workflows import create_pull_request
    try:
        return create_pull_request(conn, change_id)
    except (PermissionError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/incidents/{incident_id}/deploy")
def ops_deploy(incident_id: int, body: DeployBody, conn=Depends(get_db), user=Depends(require_supervisor)):
    from ..ops_workflows import deploy
    try:
        return deploy(conn, incident_id, body.code_change_id, body.approval_id, body.environment)
    except (PermissionError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@internal_router.post("/signals")
def internal_signal(body: SignalBody, authorization: str | None = Header(default=None), conn=Depends(get_db)):
    expected = settings.beresin_monitoring_token
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not expected or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=403, detail="Monitoring credential tidak valid.")
    try:
        return ingest_signal(conn, source=body.source, title=body.title, severity=body.severity, summary=body.summary, resource=body.resource, details=body.details)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@internal_router.get("/health")
def internal_ops_health(authorization: str | None = Header(default=None), conn=Depends(get_db)):
    from datetime import datetime, timezone
    expected = settings.beresin_monitoring_token
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not expected or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=403, detail="Monitoring credential tidak valid.")

    def age_seconds(key: str):
        row = conn.execute("SELECT updated_at FROM ops_policies WHERE key=?", (key,)).fetchone()
        if not row:
            return None
        return max(0, int((datetime.now(timezone.utc) - datetime.fromisoformat(row["updated_at"])).total_seconds()))

    operations_age = age_seconds("monitor.operations.heartbeat")
    worker_age = age_seconds("worker.conversation.heartbeat") if settings.beresin_redis_url else 0
    operations_ok = operations_age is not None and operations_age <= 180
    worker_ok = worker_age is not None and worker_age <= 30
    return {
        "status": "healthy" if operations_ok and worker_ok else "degraded",
        "operations_heartbeat_age_seconds": operations_age,
        "worker_heartbeat_age_seconds": worker_age,
        "operations_ok": operations_ok,
        "worker_ok": worker_ok,
    }
