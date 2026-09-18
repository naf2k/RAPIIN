"""Authentication routes - /api/auth/*."""
from __future__ import annotations

import os
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from ..audit import record_audit
from ..database import utcnow_iso
from ..devices import get_device_by_name_for_user, register_device
from ..security import (
    generate_token,
    hash_password,
    hash_token,
    token_expiry,
    verify_password,
    password_is_strong,
    login_is_blocked,
    record_login_failure,
    clear_login_failures,
)
from .deps import get_db, require_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    name: str
    password: str
    device_name: str
    os: str | None = None
    agent_version: str | None = None


class HeartbeatRequest(BaseModel):
    device_key: str


class DeviceRegisterRequest(BaseModel):
    device_name: str
    os: str | None = None
    agent_version: str | None = None
    capabilities: list[str] | None = None
    workspace_root: str | None = None
    allowed_roots: list[str] | None = None


def _issue_token(conn, user_id: int) -> str:
    token = generate_token()
    conn.execute(
        "INSERT INTO auth_tokens (user_id, token_hash, expires_at, created_at) VALUES (?, ?, ?, ?)",
        (user_id, hash_token(token), token_expiry(), utcnow_iso()),
    )
    return token


def _seed_supervisor(conn) -> None:
    from ..config import settings

    email = settings.beresin_init_supervisor_email
    row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if row:
        return
    conn.execute(
        "INSERT INTO users (email, password_hash, name, role, is_active, created_at) VALUES (?, ?, ?, ?, 1, ?)",
        (email, hash_password(settings.beresin_init_supervisor_password), "Supervisor BERESIN", "SUPERVISOR", utcnow_iso()),
    )


@router.post("/register")
def register(body: RegisterRequest, conn=Depends(get_db)):
    from ..config import settings
    if not settings.beresin_allow_public_registration:
        raise HTTPException(status_code=403, detail="Registrasi publik dinonaktifkan. Hubungi supervisor untuk pembuatan akun.")
    _seed_supervisor(conn)
    existing = conn.execute("SELECT id FROM users WHERE email = ?", (body.email,)).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail="Email sudah terdaftar.")
    if not password_is_strong(body.password):
        raise HTTPException(status_code=422, detail="Kata sandi minimal 12 karakter dan harus memuat huruf besar, huruf kecil, serta angka.")
    cur = conn.execute(
        "INSERT INTO users (email, password_hash, name, role, is_active, created_at) VALUES (?, ?, ?, 'USER', 1, ?)",
        (body.email, hash_password(body.password), body.name, utcnow_iso()),
    )
    user_id = cur.lastrowid
    device = register_device(
        conn,
        user_id=user_id,
        device_name=body.device_name,
        os_name=body.os,
        agent_version=body.agent_version,
    )
    device_row = conn.execute("SELECT * FROM devices WHERE id = ?", (device["device_id"],)).fetchone()
    device_info = dict(device_row)
    device_info["device_key"] = device["device_key"]
    token = _issue_token(conn, user_id)
    record_audit(
        conn,
        actor=body.name,
        actor_role="USER",
        user_id=user_id,
        device_id=device["device_id"],
        action="user_registered",
        resource=f"user:{user_id}",
    )
    return {"token": token, "user_id": user_id, "device": device_info}


@router.post("/login")
def login(body: LoginRequest, conn=Depends(get_db)):
    _seed_supervisor(conn)
    if login_is_blocked(conn, body.email):
        raise HTTPException(status_code=429, detail="Terlalu banyak percobaan masuk. Coba lagi dalam 15 menit.")
    row = conn.execute("SELECT * FROM users WHERE email = ?", (body.email,)).fetchone()
    if not row or not verify_password(body.password, row["password_hash"]):
        record_login_failure(conn, body.email)
        record_audit(
            conn,
            actor=body.email,
            actor_role="UNKNOWN",
            user_id=None,
            device_id=None,
            action="login_failed",
            resource="auth",
            result="FAILED",
            error="Invalid credentials",
        )
        # HTTPException makes the request dependency roll back; persist the
        # security counter and audit event before returning the 401.
        conn.commit()
        raise HTTPException(status_code=401, detail="Email atau kata sandi salah.")
    if not row["is_active"]:
        raise HTTPException(status_code=403, detail="Akun tidak aktif.")
    clear_login_failures(conn, body.email)
    token = _issue_token(conn, row["id"])
    record_audit(
        conn,
        actor=row["name"],
        actor_role=row["role"],
        user_id=row["id"],
        action="login",
        resource="auth",
    )
    return {"token": token, "user_id": row["id"], "name": row["name"], "role": row["role"]}


@router.post("/logout")
def logout(user=Depends(require_user), conn=Depends(get_db)):
    token = user.get("token_hash")
    conn.execute("DELETE FROM auth_tokens WHERE token_hash = ?", (token,))
    return {"status": "ok"}


@router.post("/register-device")
def register_device_route(body: DeviceRegisterRequest, user=Depends(require_user), conn=Depends(get_db)):
    from ..devices import _hash_device_key

    existing = get_device_by_name_for_user(conn, user["id"], body.device_name)
    if existing:
        # Rotate the device key so the desktop agent can (re)pair this device.
        new_key = os.urandom(32).hex()
        conn.execute(
            "UPDATE devices SET device_key_hash = ?, os = ?, agent_version = ?, capabilities = ?, workspace_root = ?, allowed_roots = ?, status = 'ONLINE', last_heartbeat_at = ? WHERE id = ?",
            (_hash_device_key(new_key), body.os, body.agent_version, json.dumps(body.capabilities or []), body.workspace_root, json.dumps(body.allowed_roots or []), utcnow_iso(), existing["id"]),
        )
        record_audit(
            conn,
            actor=user["name"],
            actor_role=user["role"],
            user_id=user["id"],
            device_id=existing["id"],
            action="device_rekeyed",
            resource=f"device:{existing['id']}",
        )
        return {"device_id": existing["id"], "device_key": new_key, "rotated": True}
    device = register_device(
        conn,
        user_id=user["id"],
        device_name=body.device_name,
        os_name=body.os,
        agent_version=body.agent_version,
        capabilities=json.dumps(body.capabilities or []),
        workspace_root=body.workspace_root,
        allowed_roots=body.allowed_roots,
    )
    return device


@router.post("/heartbeat")
def heartbeat(body: HeartbeatRequest, conn=Depends(get_db)):
    from ..devices import heartbeat as do_heartbeat

    device = do_heartbeat(conn, body.device_key)
    if not device:
        raise HTTPException(status_code=404, detail="Perangkat tidak dikenal.")
    return {"device_id": device["id"], "status": device["status"]}


class DeviceRevokeRequest(BaseModel):
    device_id: int


@router.post("/revoke-device")
def revoke_device(body: DeviceRevokeRequest, user=Depends(require_user), conn=Depends(get_db)):
    """Remove a device owned by the user (logout that machine)."""
    row = conn.execute(
        "SELECT id FROM devices WHERE id = ? AND user_id = ?", (body.device_id, user["id"])
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Perangkat tidak ditemukan.")
    # Every table with a foreign key to devices must be cleared first, otherwise
    # PostgreSQL refuses the delete and the device can never be revoked.
    conn.execute("DELETE FROM agent_jobs WHERE device_id = ?", (body.device_id,))
    conn.execute("DELETE FROM conversation_jobs WHERE device_id = ?", (body.device_id,))
    conn.execute("DELETE FROM agent_files WHERE device_id = ?", (body.device_id,))
    # Task history is kept for audit; it simply stops pointing at the device.
    conn.execute("UPDATE tasks SET device_id = NULL WHERE device_id = ?", (body.device_id,))
    conn.execute("DELETE FROM devices WHERE id = ?", (body.device_id,))
    record_audit(
        conn,
        actor=user["name"],
        actor_role="USER",
        user_id=user["id"],
        action="device_revoked",
        resource=f"device:{body.device_id}",
    )
    return {"status": "ok", "device_id": body.device_id}


@router.get("/me")
def me(user=Depends(require_user)):
    return {"user_id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"]}
