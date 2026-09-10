"""Shared pytest fixtures. Environment is set BEFORE beresin is imported so the
cached Settings object points at a fresh database for the whole session."""
import os
import tempfile
from pathlib import Path

import pytest

# Set env before any beresin import happens.
TEST_DIR = Path(tempfile.mkdtemp(prefix="beresin-test-"))
os.environ["BERESIN_DB_PATH"] = str(TEST_DIR / "test.db")
os.environ["BERESIN_DATA_DIR"] = str(TEST_DIR)
os.environ["BERESIN_ENV"] = "test"
TEST_DATABASE_URL = os.environ.get("BERESIN_TEST_DATABASE_URL", "")
if TEST_DATABASE_URL:
    os.environ["BERESIN_DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["BERESIN_EMBEDDED_QUEUE_WORKER"] = "true"
else:
    # The application loads server/.env by absolute path. Explicitly override
    # production backends so a local pytest run can never mutate the live DB.
    os.environ["BERESIN_DATABASE_URL"] = ""
    os.environ["BERESIN_REDIS_URL"] = ""
    os.environ["BERESIN_EMBEDDED_QUEUE_WORKER"] = "false"
os.environ["OPS_AGENTS_ENABLED"] = "false"
os.environ["BERESIN_ALLOW_PUBLIC_REGISTRATION"] = "true"
os.environ["BERESIN_INIT_SUPERVISOR_EMAIL"] = "supervisor@beresin.example.com"
os.environ["BERESIN_INIT_SUPERVISOR_PASSWORD"] = "Supervisor123!"
os.environ["BERESIN_INIT_SUPERVISOR_PASSWORD_FILE"] = ""
os.environ["BERESIN_SECRET_KEY"] = "dev-secret-change-me"
os.environ["BERESIN_SECRET_KEY_FILE"] = ""
os.environ["BERESIN_MONITORING_TOKEN_FILE"] = ""
os.environ["AI_API_KEY_FILE"] = ""
os.environ["OPS_TELEGRAM_BOT_TOKEN_FILE"] = ""


@pytest.fixture(autouse=True)
def _reset_db():
    """Drop all tables before each test so tests are isolated."""
    from beresin.database import connect, init_db, SCHEMA

    if TEST_DATABASE_URL:
        import psycopg
        with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as reset:
            reset.execute("DROP SCHEMA public CASCADE")
            reset.execute("CREATE SCHEMA public")
        conn = init_db()
        from beresin.main import seed_supervisor
        seed_supervisor(conn)
        conn.commit()
        conn.close()
        yield
        return

    db_path = Path(os.environ["BERESIN_DB_PATH"])
    db_path.unlink(missing_ok=True)
    conn = connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()

    from beresin.main import seed_supervisor

    conn = connect(db_path)
    seed_supervisor(conn)
    conn.commit()
    conn.close()
    yield


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from beresin.main import app

    with TestClient(app) as c:
        yield c
