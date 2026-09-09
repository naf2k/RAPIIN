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


class ApprovalBody(BaseModel):
    decision: str
    note: str = Field(default="", max_length=4000)


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
        return create_proposal(conn, incident_id, action_type=body.action_type, title=body.title, description=body.description, risk=body.risk, actor=user)
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
