#!/usr/bin/env python3
"""Bounded, non-destructive HTTP load probe for a staging BERESIN API."""
from __future__ import annotations

import argparse
import concurrent.futures
import statistics
import time

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--requests", type=int, default=500)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--confirm-staging", action="store_true")
    args = parser.parse_args()
    if not args.confirm_staging:
        raise SystemExit("Refusing to run without --confirm-staging")
    if not (1 <= args.requests <= 10_000 and 1 <= args.concurrency <= 100):
        raise SystemExit("requests must be 1..10000 and concurrency 1..100")
    url = args.base_url.rstrip("/") + "/ready"

    def request_once(_index: int):
        started = time.monotonic()
        try:
            response = httpx.get(url, timeout=10)
            ok = response.status_code == 200
        except httpx.HTTPError:
            ok = False
        return ok, (time.monotonic() - started) * 1000

    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = list(pool.map(request_once, range(args.requests)))
    latencies = sorted(item[1] for item in results)
    failures = sum(1 for ok, _latency in results if not ok)
    p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))]
    elapsed = time.monotonic() - started
    print(f"requests={args.requests} failures={failures} p50_ms={statistics.median(latencies):.1f} p95_ms={p95:.1f} rps={args.requests / elapsed:.1f}")
    return 1 if failures or p95 > 1000 else 0


if __name__ == "__main__":
    raise SystemExit(main())
