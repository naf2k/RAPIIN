"""RAPIIN FastAPI application entrypoint."""
from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from .api import agent_routes, auth_routes, ops_routes, supervisor_routes, user_routes
from .config import settings
from .database import connect, init_db, utcnow_iso
from .devices import mark_stale_devices_offline
from .security import hash_password


def seed_supervisor(conn) -> None:
    """Create the initial supervisor account if it does not exist yet."""
    email = settings.rapiin_init_supervisor_email
    existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        return
    conn.execute(
        """
        INSERT INTO users (email, password_hash, name, role, is_active, created_at)
        VALUES (?, ?, 'Supervisor RAPIIN', 'SUPERVISOR', 1, ?)
        """,
        (email, hash_password(settings.rapiin_init_supervisor_password), utcnow_iso()),
    )


async def _device_monitor_loop() -> None:
    """Periodically mark devices offline when their heartbeat is stale."""
    while True:
        try:
            await asyncio.to_thread(_device_monitor_tick)
        except Exception:  # noqa: BLE001 - keep the loop alive
            logger.exception("Device monitor tick failed")
        await asyncio.sleep(30)


def _device_monitor_tick() -> None:
    """Run one device-maintenance cycle without blocking the ASGI event loop."""
    conn = connect()
    try:
        mark_stale_devices_offline(conn)
        from .agent_jobs import requeue_expired_jobs
        requeue_expired_jobs(conn)
        from .approval import sweep_zombie_tasks
        sweep_zombie_tasks(conn)
        conn.commit()
    finally:
        conn.close()


def _ops_tick() -> None:
    """One bounded Operations Center cycle outside the event loop."""
    # Schema initialization belongs to startup/migrations. Re-running DDL from
    # a periodic monitor can request relation locks and stall PostgreSQL.
    conn = connect()
    try:
        # Publish liveness before potentially slow AI triage. A Hermes call may
        # legitimately use most of OPS_AGENT_TIMEOUT_SECONDS.
        now = utcnow_iso()
        conn.execute(
            "INSERT INTO ops_policies(key,value_json,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",
            ("monitor.operations.heartbeat", '{"status":"running"}', now),
        )
        conn.commit()
        from .ops_incidents import (
            auto_resolve,
            collect_runtime_signals,
            expire_pending_approvals,
            ingest_signal,
            queue_daily_digest,
        )
        from .ops_notifications import deliver_pending
        # Each phase commits on its own. A single tick-wide transaction would
        # stay open across slow work (Telegram calls, Hermes runs) and trip
        # PostgreSQL's idle_in_transaction_session_timeout, which kills the
        # connection and aborts the rest of the tick.
        collect_runtime_signals(conn)
        expire_pending_approvals(conn)
        conn.commit()
        queue_daily_digest(conn)
        conn.commit()
        from .ops_maintenance import apply_ops_retention, queue_approval_reminders
        queue_approval_reminders(conn)
        apply_ops_retention(conn)
        conn.commit()
        deliver_pending(conn)
        if settings.ops_agents_enabled:
            from .ops_runtime import (
                capacity_available,
                dispatch_incident,
                finalize_agent_triage,
                provider_circuit_open,
                recover_expired_assignments,
                resume_pending_assignments,
            )
            recover_expired_assignments(conn)
            circuit_open = provider_circuit_open(conn)
            if circuit_open:
                ingest_signal(conn, source="ops-provider-circuit", title="Operations AI provider circuit open", severity="HIGH", summary="Kegagalan agent beruntun mencapai batas; dispatch AI dijeda otomatis.", resource="operations-provider")
            else:
                auto_resolve(conn, source="ops-provider-circuit", resource="operations-provider", note="Provider Operations Agent kembali melewati cooldown tanpa kegagalan baru.")
            for completed in conn.execute("SELECT id FROM ops_incidents WHERE status='OPEN'").fetchall():
                finalize_agent_triage(conn, completed["id"])
            if not circuit_open:
                # Resume work that was queued behind the concurrency limit.
                resume_pending_assignments(conn)
                if capacity_available(conn):
                    rows = conn.execute(
                        "SELECT i.id FROM ops_incidents i WHERE i.status IN ('OPEN','INVESTIGATING') "
                        "AND NOT EXISTS (SELECT 1 FROM ops_agent_assignments a WHERE a.incident_id=i.id AND a.status IN ('PENDING','ACTIVE')) "
                        "AND NOT EXISTS (SELECT 1 FROM ops_incident_events e WHERE e.incident_id=i.id AND e.event_type='AGENT_TRIAGE_COMPLETED') "
                        "ORDER BY CASE i.severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 ELSE 3 END, i.id LIMIT 5"
                    ).fetchall()
                    for row in rows:
                        if not capacity_available(conn):
                            break
                        dispatch_incident(conn, row["id"])
        now = utcnow_iso()
        conn.execute(
            "INSERT INTO ops_policies(key,value_json,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",
            ("monitor.operations.heartbeat", '{"status":"ok"}', now),
        )
        conn.commit()
    finally:
        conn.close()


async def _ops_monitor_loop() -> None:
    # Give PostgreSQL, Redis, and the desktop agent time to restore their
    # heartbeats after login/reboot. Without this grace period every normal
    # boot can create a false "Desktop agent offline" incident.
    await asyncio.sleep(120)
    while True:
        try:
            await asyncio.to_thread(_ops_tick)
        except Exception:  # noqa: BLE001 - core RAPIIN must survive ops failure
            logger.exception("Operations Center tick failed")
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_for_startup()
    conn = init_db()
    try:
        seed_supervisor(conn)
        from .ops_incidents import seed_ops
        seed_ops(conn)
        conn.execute(
            "INSERT INTO ops_policies(key,value_json,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",
            ("monitor.operations.heartbeat", '{"status":"starting"}', utcnow_iso()),
        )
        conn.commit()
    finally:
        conn.close()
    from .worker import recover_conversation_jobs
    recover_conversation_jobs()
    queue_stop = None
    queue_thread = None
    if settings.rapiin_redis_url and settings.rapiin_embedded_queue_worker:
        from .worker import run_queue_worker
        queue_stop = threading.Event()
        queue_thread = threading.Thread(target=run_queue_worker, args=(queue_stop,), name="rapiin-embedded-queue", daemon=True)
        queue_thread.start()
    task = asyncio.create_task(_device_monitor_loop())
    ops_task = asyncio.create_task(_ops_monitor_loop())
    yield
    task.cancel()
    ops_task.cancel()
    if queue_stop:
        queue_stop.set()
    if queue_thread:
        queue_thread.join(timeout=3)
    try:
        await task
    except asyncio.CancelledError:
        pass
    try:
        await ops_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="RAPIIN API",
    version="1.0.0",
    description="Backend RAPIIN - Hermes Core",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger("rapiin.http")


@app.middleware("http")
async def production_headers_and_request_log(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    started = time.monotonic()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
    )
    if settings.rapiin_env.lower() == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    logger.info("request_id=%s method=%s path=%s status=%s duration_ms=%.1f",
                request_id, request.method, request.url.path, response.status_code,
                (time.monotonic() - started) * 1000)
    return response


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/ready")
def ready():
    try:
        conn = connect()
        conn.execute("SELECT 1").fetchone()
        conn.close()
    except Exception:
        from fastapi.responses import JSONResponse
        return JSONResponse({"status": "not_ready", "database": "unavailable"}, status_code=503)
    try:
        from .queue_backend import redis_ready
        if not redis_ready():
            raise RuntimeError("Redis ping gagal")
    except Exception:
        from fastapi.responses import JSONResponse
        return JSONResponse({"status": "not_ready", "database": "ok", "queue": "unavailable"}, status_code=503)
    return {"status": "ready", "database": "ok", "queue": "ok" if settings.rapiin_redis_url else "inline"}


@app.get("/internal/metrics", response_class=PlainTextResponse)
def internal_metrics(request: Request):
    import hmac

    from fastapi import HTTPException
    expected = settings.rapiin_monitoring_token
    supplied = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not expected or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=403, detail="Monitoring credential tidak valid.")
    from .metrics import prometheus_metrics
    conn = connect()
    try:
        return prometheus_metrics(conn)
    finally:
        conn.close()


app.include_router(auth_routes.router)
app.include_router(user_routes.router)
app.include_router(supervisor_routes.router)
app.include_router(ops_routes.router)
app.include_router(ops_routes.internal_router)
app.include_router(agent_routes.router)
