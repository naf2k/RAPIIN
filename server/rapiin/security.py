"""Security helpers: password hashing, bearer tokens, RBAC helpers."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from .database import utcnow_iso

TOKEN_TTL = timedelta(days=7)
LOGIN_WINDOW = timedelta(minutes=15)
LOGIN_BLOCK = timedelta(minutes=15)
LOGIN_MAX_FAILURES = 5


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000)
    return f"pbkdf2${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt, hex_digest = stored.split("$", 2)
        if scheme != "pbkdf2":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000)
        return hmac.compare_digest(digest.hex(), hex_digest)
    except Exception:
        return False


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_expiry() -> str:
    return (datetime.now(timezone.utc) + TOKEN_TTL).isoformat()


def password_is_strong(password: str) -> bool:
    return len(password) >= 12 and any(c.islower() for c in password) and any(c.isupper() for c in password) and any(c.isdigit() for c in password)


def login_is_blocked(conn, identity: str) -> bool:
    row = conn.execute("SELECT blocked_until FROM login_attempts WHERE identity = ?", (identity.lower(),)).fetchone()
    return bool(row and row["blocked_until"] and row["blocked_until"] > utcnow_iso())


def record_login_failure(conn, identity: str) -> None:
    now = datetime.now(timezone.utc)
    row = conn.execute("SELECT * FROM login_attempts WHERE identity = ?", (identity.lower(),)).fetchone()
    if not row or row["window_started_at"] < (now - LOGIN_WINDOW).isoformat():
        count = 1
        started = now.isoformat()
    else:
        count = row["failed_count"] + 1
        started = row["window_started_at"]
    blocked_until = (now + LOGIN_BLOCK).isoformat() if count >= LOGIN_MAX_FAILURES else None
    conn.execute(
        "INSERT INTO login_attempts(identity, failed_count, window_started_at, blocked_until) VALUES(?,?,?,?) "
        "ON CONFLICT(identity) DO UPDATE SET failed_count=excluded.failed_count, window_started_at=excluded.window_started_at, blocked_until=excluded.blocked_until",
        (identity.lower(), count, started, blocked_until),
    )


def clear_login_failures(conn, identity: str) -> None:
    conn.execute("DELETE FROM login_attempts WHERE identity = ?", (identity.lower(),))
