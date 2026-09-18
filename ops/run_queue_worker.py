#!/usr/bin/env python3
"""Run the RAPIIN Redis-backed conversation worker."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from rapiin.config import settings
from rapiin.worker import run_queue_worker

if not settings.rapiin_redis_url:
    raise SystemExit("RAPIIN_REDIS_URL wajib dikonfigurasi untuk worker terpisah.")

# Resolve the secret from its file the same way the API does. Approval snapshot
# hashes are keyed by this secret, so a worker on a different key would create
# approvals that no one can ever decide.
settings.validate_for_startup()

try:
    run_queue_worker()
except KeyboardInterrupt:
    pass
