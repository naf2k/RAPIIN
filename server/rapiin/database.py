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
    full_auto_mode INTEGER NOT NULL DEFAULT 0,
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
    task_id INTEGER,
    previous_hash TEXT,
    event_hash TEXT
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

-- Per-user policy (Opsi B). A row here wins over the global action_policies
-- row for the same tool. Absence falls back to the global row, then to the
-- built-in default. FULL_AUTO is a separate user-level switch (users.full_auto_mode),
-- not a per-tool value, so this CHECK stays limited to the three approval kinds.
CREATE TABLE IF NOT EXISTS user_action_policies (
    user_id INTEGER NOT NULL REFERENCES users(id),
    tool_name TEXT NOT NULL,
    approval_kind TEXT NOT NULL CHECK (approval_kind IN ('AUTO','USER','SUPERVISOR')),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, tool_name)
);

-- Trash ledger: every destructive operation done without an approval moves
-- files here instead of unlinking them, so the user can undo it.
CREATE TABLE IF NOT EXISTS trash_entries (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    device_id INTEGER REFERENCES devices(id),
    task_id INTEGER,
    root TEXT,
    created_at TEXT NOT NULL,
    item_count INTEGER NOT NULL DEFAULT 0,
    restored_at TEXT,
    manifest_json TEXT
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

-- Operations Center: incident response remains separate from user file approvals.
CREATE TABLE IF NOT EXISTS ops_agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL UNIQUE CHECK (role IN ('LEAD','SECURITY','DIAGNOSTIC','CODER')),
    state TEXT NOT NULL DEFAULT 'IDLE' CHECK (state IN ('IDLE','RUNNING','PAUSED','OFFLINE')),
    model_policy TEXT NOT NULL DEFAULT '{}',
    tool_policy TEXT NOT NULL DEFAULT '{}',
    environment_scope TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT NOT NULL,
    title TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','INVESTIGATING','AWAITING_APPROVAL','APPROVED_FOR_FIX','FIXING','VERIFYING','AWAITING_DEPLOY_APPROVAL','DEPLOYING','RESOLVED','REJECTED')),
    summary TEXT,
    source TEXT NOT NULL,
    affected_resource TEXT,
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    resolved_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_incident_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id INTEGER NOT NULL REFERENCES ops_incidents(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    actor_role TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_agent_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id INTEGER NOT NULL REFERENCES ops_incidents(id) ON DELETE CASCADE,
    agent_id INTEGER NOT NULL REFERENCES ops_agents(id),
    assignment TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','ACTIVE','COMPLETED','CANCELLED')),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    lease_expires_at TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS ops_agent_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id INTEGER NOT NULL REFERENCES ops_incidents(id) ON DELETE CASCADE,
    sender_agent_id INTEGER REFERENCES ops_agents(id),
    recipient_agent_id INTEGER REFERENCES ops_agents(id),
    message_type TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_action_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id INTEGER NOT NULL REFERENCES ops_incidents(id) ON DELETE CASCADE,
    proposed_by_agent_id INTEGER REFERENCES ops_agents(id),
    action_type TEXT NOT NULL CHECK (action_type IN ('INVESTIGATION','CODE_FIX','DEPLOYMENT')),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    risk TEXT,
    scope_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','APPROVED','REJECTED','EXECUTED','CANCELLED')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id INTEGER NOT NULL REFERENCES ops_incidents(id) ON DELETE CASCADE,
    proposal_id INTEGER REFERENCES ops_action_proposals(id),
    approval_type TEXT NOT NULL CHECK (approval_type IN ('CODE_FIX','DEPLOYMENT')),
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','APPROVED','REJECTED','EXPIRED')),
    snapshot_hash TEXT,
    idempotency_key TEXT,
    expires_at TEXT,
    requested_at TEXT NOT NULL,
    decided_at TEXT,
    decided_by INTEGER REFERENCES users(id),
    decision_note TEXT
);

CREATE TABLE IF NOT EXISTS ops_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id INTEGER REFERENCES ops_incidents(id) ON DELETE CASCADE,
    audience TEXT NOT NULL DEFAULT 'OWNER',
    channel TEXT NOT NULL DEFAULT 'IN_APP',
    title TEXT NOT NULL,
    body TEXT,
    severity TEXT NOT NULL,
    is_read INTEGER NOT NULL DEFAULT 0,
    delivery_status TEXT NOT NULL DEFAULT 'PENDING' CHECK (delivery_status IN ('PENDING','SENT','FAILED','SKIPPED')),
    delivered_at TEXT,
    last_error TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_policies (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_by INTEGER REFERENCES users(id),
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id INTEGER NOT NULL REFERENCES ops_incidents(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    source TEXT NOT NULL,
    content_json TEXT NOT NULL DEFAULT '{}',
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_code_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id INTEGER NOT NULL REFERENCES ops_incidents(id) ON DELETE CASCADE,
    approval_id INTEGER NOT NULL REFERENCES ops_approvals(id),
    branch_name TEXT NOT NULL,
    worktree_path TEXT NOT NULL,
    base_commit TEXT NOT NULL,
    commit_sha TEXT,
    pull_request_url TEXT,
    diff_summary TEXT,
    status TEXT NOT NULL DEFAULT 'PROVISIONED' CHECK (status IN ('PROVISIONED','RUNNING','READY_FOR_REVIEW','FAILED','CANCELLED')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_check_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code_change_id INTEGER NOT NULL REFERENCES ops_code_changes(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PENDING','RUNNING','PASSED','FAILED','SKIPPED')),
    command TEXT,
    output_summary TEXT,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS ops_deployments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id INTEGER NOT NULL REFERENCES ops_incidents(id),
    code_change_id INTEGER NOT NULL REFERENCES ops_code_changes(id),
    approval_id INTEGER NOT NULL REFERENCES ops_approvals(id),
    environment TEXT NOT NULL,
    artifact_ref TEXT NOT NULL,
    previous_artifact_ref TEXT,
    status TEXT NOT NULL CHECK (status IN ('PENDING','DEPLOYING','VERIFYING','SUCCEEDED','FAILED','ROLLED_BACK')),
    health_result_json TEXT,
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_agent_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER NOT NULL REFERENCES ops_agents(id),
    incident_id INTEGER REFERENCES ops_incidents(id),
    duration_ms INTEGER NOT NULL DEFAULT 0,
    prompt_chars INTEGER NOT NULL DEFAULT 0,
    output_chars INTEGER NOT NULL DEFAULT 0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    api_calls INTEGER NOT NULL DEFAULT 0,
    estimated_cost_usd REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ops_incidents_status_severity ON ops_incidents(status, severity, last_seen_at);
CREATE INDEX IF NOT EXISTS idx_ops_incidents_fingerprint ON ops_incidents(fingerprint, status);
CREATE INDEX IF NOT EXISTS idx_ops_events_incident ON ops_incident_events(incident_id, id);
CREATE INDEX IF NOT EXISTS idx_ops_approvals_status ON ops_approvals(status, requested_at);
CREATE INDEX IF NOT EXISTS idx_ops_assignments_status ON ops_agent_assignments(status, created_at);
CREATE INDEX IF NOT EXISTS idx_ops_code_changes_incident ON ops_code_changes(incident_id, id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_approvals_pending_dedupe ON approvals(user_id, kind, status, COALESCE(task_id, -1), COALESCE(tool_name, ''), COALESCE(snapshot_hash, '')) WHERE status = 'PENDING';
"""


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(db_path: Path | None = None):
    if settings.rapiin_database_url and db_path is None:
        import psycopg
        from psycopg.rows import dict_row

        from .postgres_support import PostgresConnection

        return PostgresConnection(
            psycopg.connect(
                settings.rapiin_database_url,
                row_factory=dict_row,
                # Defense in depth: terminate forgotten transactions and fail
                # boundedly on locks instead of freezing the service forever.
                options="-c idle_in_transaction_session_timeout=30000 -c lock_timeout=5000",
            )
        )
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
    "ALTER TABLE ops_notifications ADD COLUMN delivery_status TEXT NOT NULL DEFAULT 'PENDING'",
    "ALTER TABLE ops_notifications ADD COLUMN delivered_at TEXT",
    "ALTER TABLE ops_notifications ADD COLUMN last_error TEXT",
    "ALTER TABLE ops_notifications ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE ops_notifications ADD COLUMN next_attempt_at TEXT",
    "ALTER TABLE ops_approvals ADD COLUMN idempotency_key TEXT",
    "ALTER TABLE ops_approvals ADD COLUMN expires_at TEXT",
    "ALTER TABLE ops_agent_assignments ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE ops_agent_assignments ADD COLUMN lease_expires_at TEXT",
    "ALTER TABLE ops_agent_usage ADD COLUMN input_tokens INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE ops_agent_usage ADD COLUMN output_tokens INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE ops_agent_usage ADD COLUMN api_calls INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE ops_agent_usage ADD COLUMN estimated_cost_usd REAL NOT NULL DEFAULT 0",
    "ALTER TABLE audit_log ADD COLUMN previous_hash TEXT",
    "ALTER TABLE audit_log ADD COLUMN event_hash TEXT",
    "ALTER TABLE users ADD COLUMN full_auto_mode INTEGER NOT NULL DEFAULT 0",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_ops_approvals_idempotency ON ops_approvals(idempotency_key) WHERE idempotency_key IS NOT NULL",
    "DROP INDEX IF EXISTS idx_approvals_pending_lookup",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_approvals_pending_dedupe ON approvals(user_id, kind, status, COALESCE(task_id, -1), COALESCE(tool_name, ''), COALESCE(snapshot_hash, '')) WHERE status = 'PENDING'",
]


def _migrate(conn) -> None:
    """Apply additive migrations idempotently (existing DBs only)."""
    for statement in MIGRATIONS:
        try:
            conn.execute(statement)
        except sqlite3.OperationalError:
            pass  # column already present


# Postgres needs ADD COLUMN IF NOT EXISTS; SQLite does not support that syntax,
# which is why the two migration lists are kept apart.
POSTGRES_MIGRATIONS = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS full_auto_mode INTEGER NOT NULL DEFAULT 0",
]


def _migrate_postgres(conn) -> None:
    for statement in POSTGRES_MIGRATIONS:
        try:
            conn.execute(statement)
        except Exception:  # noqa: BLE001 - column already present or dialect quirk
            pass


def init_db() -> sqlite3.Connection:
    conn = connect()
    if settings.rapiin_database_url:
        from .postgres_support import postgres_schema
        conn.executescript(postgres_schema(SCHEMA))
        _migrate_postgres(conn)
    else:
        conn.executescript(SCHEMA)
        _migrate(conn)
    from .audit import backfill_audit_chain
    backfill_audit_chain(conn)
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
