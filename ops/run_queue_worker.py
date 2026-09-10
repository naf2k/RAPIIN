#!/usr/bin/env python3
"""Run the BERESIN Redis-backed conversation worker."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from beresin.config import settings
from beresin.worker import run_queue_worker

if not settings.beresin_redis_url:
    raise SystemExit("BERESIN_REDIS_URL wajib dikonfigurasi untuk worker terpisah.")

try:
    run_queue_worker()
except KeyboardInterrupt:
    pass
