"""FastAPI dependencies - DB session, current user, RBAC."""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException

from ..database import db_session, utcnow_iso
from ..security import hash_token

# sqlite3 connections are recreated per request by db_session. We expose a
# connection provider that commits after the request completes.


def get_db():
    with db_session() as conn:
        yield conn


def authenticate(conn, token: str) -> dict:
    token_hash = hash_token(token)
    row = conn.execute(
        """
        SELECT u.*, a.expires_at, a.token_hash
        FROM auth_tokens a JOIN users u ON u.id = a.user_id
        WHERE a.token_hash = ? LIMIT 1
        """,
        (token_hash,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Token tidak valid.")
    if row["expires_at"] < utcnow_iso():
        raise HTTPException(status_code=401, detail="Sesi berakhir. Silakan masuk kembali.")
    if not row["is_active"]:
        raise HTTPException(status_code=403, detail="Akun tidak aktif.")
    return dict(row)


def require_user(conn=Depends(get_db), authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Autentikasi diperlukan.")
    token = authorization.split(" ", 1)[1].strip()
    user = authenticate(conn, token)
    return user


def require_supervisor(conn=Depends(get_db), authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Autentikasi diperlukan.")
    token = authorization.split(" ", 1)[1].strip()
    user = authenticate(conn, token)
    if user["role"] != "SUPERVISOR":
        raise HTTPException(status_code=403, detail="Akses khusus supervisor.")
    return user
