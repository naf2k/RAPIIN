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


@pytest.fixture(autouse=True)
def _reset_db():
    """Drop all tables before each test so tests are isolated."""
    from beresin.database import connect, SCHEMA

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
