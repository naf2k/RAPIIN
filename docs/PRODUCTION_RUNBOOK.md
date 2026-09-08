# BERESIN Production Runbook

## Supported release topology

V1 supports one API instance with its SQLite database on a local persistent volume. Do not mount SQLite on NFS and do not run multiple API replicas against one database. Horizontal API scaling requires a PostgreSQL adapter and external durable queue; that is a post-V1 architecture gate, not a safe configuration switch.

## Deploy

1. Create production secrets outside Git and set every required variable in `docker-compose.yml`.
2. Terminate TLS at the reverse proxy and set `BERESIN_ALLOWED_ORIGINS` to exact HTTPS origins.
3. Run `docker compose build --pull` and scan the resulting image.
4. Run `docker compose up -d`, then require `/health` and `/ready` to return HTTP 200.
5. Verify login, one read-only device task, approval review, an approved move in a disposable folder, and audit visibility.

The production topology is defined in `docker-compose.production.yml` with Caddy TLS and Prometheus scraping. Create a protected directory containing four files (`beresin_secret_key`, `supervisor_password`, `monitoring_token`, `ai_api_key`), each readable only by the deployment operator. Then set `BERESIN_SECRETS_DIR`, `BERESIN_DOMAIN`, `BERESIN_INIT_SUPERVISOR_EMAIL`, `AI_BASE_URL`, and run:

```bash
docker compose -f docker-compose.production.yml config
docker compose -f docker-compose.production.yml up --build -d
curl --fail https://YOUR_DOMAIN/ready
```

Validate the live provider without sending files:

```bash
AI_BASE_URL=https://provider.example/v1 AI_API_KEY=... server/.venv/bin/python ops/provider_smoke.py
```

Run `ops/load_test.py` only against an authorized staging deployment and include `--confirm-staging`.

The container runs as UID 10001, drops Linux capabilities, uses a read-only root filesystem, and writes only to the persistent data volume and temporary memory filesystem.

## Backup and restore drill

Create a transactionally consistent backup:

```bash
python3 ops/backup_sqlite.py server/data/beresin.db /secure/beresin-backups
```

Restore drills must target a new path, never overwrite the live database:

```bash
python3 ops/restore_sqlite.py /secure/beresin-backups/beresin-TIMESTAMP.db /tmp/beresin-restore.db
sqlite3 /tmp/beresin-restore.db 'PRAGMA integrity_check;'
```

Encrypt backups at rest, restrict them to operations staff, retain them according to company policy, and test a restore before every production release.

## Incident response

- AI outage: tasks fail with a user-safe message; inspect failure metrics and upstream status, then retry only idempotent/read operations.
- Agent outage: do not execute against server storage. Restore connectivity, verify the device identity, and allow leased jobs to requeue.
- Suspected device-key exposure: revoke the device in User Settings and pair it again to rotate credentials.
- Unexpected file result: stop the agent, preserve audit/task/job records, and do not retry a destructive action until its snapshot is reviewed again.
- Database issue: stop the API, preserve the database plus WAL/SHM files, validate the latest backup, and restore to a new volume.

## Rollback

Keep the prior immutable image tag. Stop the new container, back up the current database, and start the prior image only if its schema is backward compatible. Additive migrations in V1 are compatible, but rollback must still be rehearsed against a restored backup.

## Release automation

- `.github/workflows/ci.yml`: backend matrices, agent OS/Python matrices, UI/accessibility, Docker build and Trivy scan.
- `.github/workflows/security.yml`: secret, dependency, configuration and Bandit scans.
- `.github/workflows/release-agent.yml`: builds the terminal-installable Python wheel, verifies installation across supported OS/Python versions, generates checksums, and publishes tagged releases. Native application signing/notarization is intentionally out of scope.
- `ops/release_gate.py`: reproducible local gate report.
