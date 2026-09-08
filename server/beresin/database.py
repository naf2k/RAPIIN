"""SQLite access layer with an explicit schema (V1)."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .config import settings

SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('USER', 'SUPERVISOR')),
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    device_name TEXT NOT NULL,
    device_key_hash TEXT NOT NULL,
    os TEXT,
    agent_version TEXT,
    status TEXT NOT NULL DEFAULT 'OFFLINE' CHECK (status IN ('ONLINE', 'OFFLINE')),
    last_heartbeat_at TEXT,
    capabilities TEXT,
    workspace_root TEXT,
    allowed_roots TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id),
    role TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    tool_name TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    device_id INTEGER REFERENCES devices(id),
    type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'PLANNING', 'WAITING_APPROVAL', 'RUNNING',
                          'VERIFYING', 'COMPLETED', 'FAILED', 'CANCELLED')),
    progress REAL NOT NULL DEFAULT 0,
    processed_count INTEGER NOT NULL DEFAULT 0,
    total_count INTEGER NOT NULL DEFAULT 0,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    result_json TEXT,
    error TEXT,
    approval_status TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER REFERENCES tasks(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    requested_by TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('USER', 'SUPERVISOR')),
    action TEXT NOT NULL,
    scope TEXT,
    risk TEXT,
    tool_name TEXT,
    tool_args TEXT,
    snapshot_hash TEXT,
    expires_at TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED')),
    decided_by INTEGER REFERENCES users(id),
    decided_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS login_attempts (
    identity TEXT PRIMARY KEY,
    failed_count INTEGER NOT NULL DEFAULT 0,
    window_started_at TEXT NOT NULL,
    blocked_until TEXT
);

CREATE TABLE IF NOT EXISTS metric_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    value REAL NOT NULL,
    timestamp TEXT NOT NULL,
    tags TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT,
    actor_role TEXT,
    user_id INTEGER,
    device_id INTEGER,
    action TEXT NOT NULL,
    resource TEXT,
    timestamp TEXT NOT NULL,
    result TEXT NOT NULL,
    error TEXT,
    approval_id INTEGER,
    task_id INTEGER
);

CREATE TABLE IF NOT EXISTS memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    kind TEXT NOT NULL DEFAULT 'private',
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (user_id, kind, key)
);

CREATE TABLE IF NOT EXISTS agent_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    device_id INTEGER,
    path TEXT NOT NULL,
    file_hash TEXT,
    size INTEGER,
    mtime REAL,
    extracted_text TEXT,
    indexed_at TEXT NOT NULL,
    UNIQUE (user_id, device_id, path)
);

CREATE TABLE IF NOT EXISTS agent_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER REFERENCES tasks(id),
    device_id INTEGER REFERENCES devices(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'CLAIMED', 'SUCCEEDED', 'FAILED')),
    result_json TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    claimed_at TEXT,
    finished_at TEXT,
    lease_expires_at TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    idempotency_key TEXT UNIQUE
);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    role TEXT NOT NULL CHECK (role IN ('USER', 'SUPERVISOR')),
    title TEXT NOT NULL,
    body TEXT,
    type TEXT NOT NULL DEFAULT 'info' CHECK (type IN ('info', 'success', 'error', 'warning')),
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    task_id INTEGER
);

CREATE TABLE IF NOT EXISTS user_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (user_id, key)
);

CREATE TABLE IF NOT EXISTS action_policies (
    tool_name TEXT PRIMARY KEY,
    approval_kind TEXT NOT NULL CHECK (approval_kind IN ('AUTO','USER','SUPERVISOR')),
    bulk_threshold INTEGER NOT NULL DEFAULT 20,
    updated_by INTEGER REFERENCES users(id),
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversation_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL UNIQUE REFERENCES tasks(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    conversation_id INTEGER NOT NULL REFERENCES conversations(id),
    device_id INTEGER REFERENCES devices(id),
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','CLAIMED','SUCCEEDED','FAILED')),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    lease_expires_at TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    finished_at TEXT
);
"""


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    # busy_timeout lets concurrent writers (server + desktop agents) wait for
    # the lock instead of failing immediately with "database is locked".
    conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return conn


MIGRATIONS = [
    # approval resume support: store which tool + args an approval gates.
    "ALTER TABLE approvals ADD COLUMN tool_name TEXT",
    "ALTER TABLE approvals ADD COLUMN tool_args TEXT",
    "ALTER TABLE approvals ADD COLUMN snapshot_hash TEXT",
    "ALTER TABLE approvals ADD COLUMN expires_at TEXT",
    "ALTER TABLE tasks ADD COLUMN processed_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE tasks ADD COLUMN total_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE tasks ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE agent_jobs ADD COLUMN lease_expires_at TEXT",
    "ALTER TABLE agent_jobs ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE agent_jobs ADD COLUMN idempotency_key TEXT",
    "ALTER TABLE devices ADD COLUMN workspace_root TEXT",
    "ALTER TABLE devices ADD COLUMN allowed_roots TEXT",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_jobs_idempotency ON agent_jobs(idempotency_key) WHERE idempotency_key IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_agent_jobs_device_status ON agent_jobs(device_id, status, id)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_status_created ON tasks(status, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_devices_status_heartbeat ON devices(status, last_heartbeat_at)",
    "CREATE INDEX IF NOT EXISTS idx_metric_events_name_time ON metric_events(name, timestamp)",
]


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply additive migrations idempotently (existing DBs only)."""
    for statement in MIGRATIONS:
        try:
            conn.execute(statement)
        except sqlite3.OperationalError:
            pass  # column already present


def init_db() -> sqlite3.Connection:
    conn = connect()
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()
    return conn


@contextmanager
def db_session():
    # Schema initialization belongs to application startup. Running the full
    # DDL script for every HTTP request takes SQLite schema/write locks and can
    # stall health checks, agent heartbeats, and task polling during AI work.
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
