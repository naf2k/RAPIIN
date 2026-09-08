# Capacity and Scaling Decision

## Supported V1 envelope

The production configuration intentionally supports one BERESIN API instance, one local persistent SQLite volume, and many independently polling Desktop Agents. This avoids unsafe multi-writer/network-filesystem assumptions while keeping scanning and hashing on employee devices.

Release targets:

- `/ready` staging probe: zero failures and p95 below 1 second at 20 concurrent requests.
- File validation: at least 1,000 files per scan; the agent hard limit is 5,000 files per operation.
- Queue validation: at least two concurrent devices with strict job ownership.
- AI requests: bounded by provider timeout, three transient retries, and persistent task status.

Run the bounded staging probe:

```bash
server/.venv/bin/python ops/load_test.py --base-url https://staging.example.com --requests 500 --concurrency 20 --confirm-staging
```

## Mandatory scale-up trigger

Move to PostgreSQL plus an external durable queue before any of the following:

- more than one API replica;
- SQLite lock timeouts under representative load;
- queue recovery or monitoring requires cross-host workers;
- database growth, backup time, or recovery objectives exceed the single-volume operational target.

The migration must preserve user/device ownership constraints, idempotency keys, job leases, approval snapshots, and append-only audit semantics. Do not place the current SQLite file on NFS or a shared network volume.
