"""BERESIN FastAPI application entrypoint."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse

from .api import agent_routes, auth_routes, supervisor_routes, user_routes
from .config import settings
from .database import connect, init_db
from .devices import mark_stale_devices_offline
from .security import hash_password

# Frontend lives one level above the server package root.
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent


def seed_supervisor(conn) -> None:
    """Create the initial supervisor account if it does not exist yet."""
    email = settings.beresin_init_supervisor_email
    existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        return
    conn.execute(
        """
        INSERT INTO users (email, password_hash, name, role, is_active, created_at)
        VALUES (?, ?, 'Supervisor BERESIN', 'SUPERVISOR', 1, datetime('now'))
        """,
        (email, hash_password(settings.beresin_init_supervisor_password)),
    )


async def _device_monitor_loop() -> None:
    """Periodically mark devices offline when their heartbeat is stale."""
    while True:
        try:
            conn = init_db()
            try:
                mark_stale_devices_offline(conn)
                from .agent_jobs import requeue_expired_jobs
                requeue_expired_jobs(conn)
                conn.commit()
            finally:
                conn.close()
        except Exception:  # noqa: BLE001 - keep the loop alive
            pass
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_for_startup()
    conn = init_db()
    try:
        seed_supervisor(conn)
        conn.commit()
    finally:
        conn.close()
    from .worker import recover_conversation_jobs
    recover_conversation_jobs()
    task = asyncio.create_task(_device_monitor_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="BERESIN API",
    version="1.0.0",
    description="Backend BERESIN - Hermes Core",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger("beresin.http")


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
    if settings.beresin_env.lower() == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    logger.info("request_id=%s method=%s path=%s status=%s duration_ms=%.1f",
                request_id, request.method, request.url.path, response.status_code,
                (time.monotonic() - started) * 1000)
    return response


@app.get("/")
def root():
    return {"app": "BERESIN", "status": "ok"}


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
    return {"status": "ready", "database": "ok"}


@app.get("/internal/metrics", response_class=PlainTextResponse)
def internal_metrics(request: Request):
    import hmac
    from fastapi import HTTPException
    expected = settings.beresin_monitoring_token
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
app.include_router(agent_routes.router)

# Serve the static frontend (HTML/CSS/JS). API routes are registered first,
# so this catch-all only handles non-API paths.


@app.get("/{full_path:path}", include_in_schema=False)
def frontend_fallback(full_path: str):
    candidate = (FRONTEND_DIR / full_path).resolve()
    # Prevent path traversal outside the frontend directory.
    try:
        candidate.relative_to(FRONTEND_DIR.resolve())
    except ValueError:
        candidate = FRONTEND_DIR / "index.html"
    if candidate.is_file():
        return FileResponse(str(candidate))
    return FileResponse(str(FRONTEND_DIR / "index.html"))
