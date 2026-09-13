# BERESIN Production Runbook

## Loopback-only macOS deployment

For a single-user local deployment, bind the API to `127.0.0.1` and use exact
loopback origins. This topology is not reachable from LAN or the internet, so
public-domain TLS and Windows validation are not applicable. Keep the server,
agent, health monitor, queue worker, and daily backup as separate user LaunchAgents:

- `com.beresin.server`
- `com.beresin.agent`
- `com.beresin.worker`
- `com.beresin.monitor`
- `com.beresin.backup`

The monitor runs `ops/local_health_monitor.py` every minute and emits a macOS
notification only when readiness changes. The daily backup targets
`~/BeresinBackups`. Run `server/.venv/bin/python ops/local_uat.py` for a
credentialed local smoke test. Secret and UAT credential files remain ignored
under `server/data`, mode `0600`; never commit them.

Before the reboot drill run `beresin startup-probe record`. After logging in
again, run `beresin startup-probe verify`, require `/ready` to return HTTP 200,
and confirm all five LaunchAgents are present. Run the complete local readiness
gate with `server/.venv/bin/beresin-ops verify`.

## Supported release topology

The verified local P1 topology uses one API instance, PostgreSQL, Redis, and one
separate conversation worker. SQLite remains supported for development and
single-process fallback. Do not mount SQLite on NFS or scale it horizontally.

## PostgreSQL migration path

The server selects PostgreSQL with `BERESIN_DATABASE_URL` and Redis with
`BERESIN_REDIS_URL`; leaving both empty preserves SQLite/inline development
mode. Start disposable infrastructure with `docker-compose.local-infra.yml`,
migrate only into a confirmed empty target, and keep SQLite read-only during the
copy:

```bash
docker compose -f docker-compose.local-infra.yml up -d
server/.venv/bin/python ops/migrate_sqlite_to_postgres.py server/data/beresin.db \
  --database-url "$BERESIN_DATABASE_URL" --confirm-empty-target
```

The migration copies explicit IDs and advances every PostgreSQL identity sequence. Verify row counts, login, device polling, approval, AI Operations dispatch, and audit integrity before changing the live server connection. Keep the SQLite source and a transactionally consistent backup until the PostgreSQL cutover is signed off.

Run the Redis worker and readiness gate separately:

```bash
server/.venv/bin/python ops/run_queue_worker.py
server/.venv/bin/beresin-ops verify
```

## Deploy

1. Create production secrets outside Git and set every required variable in `docker-compose.yml`.
2. Terminate TLS at the reverse proxy and set `BERESIN_ALLOWED_ORIGINS` to exact HTTPS origins.
3. Run `docker compose build --pull` and scan the resulting image.
4. Run `docker compose up -d`, then require `/health` and `/ready` to return HTTP 200.
5. Verify login, one read-only device task, approval review, an approved move in a disposable folder, and audit visibility.

The production topology is defined in `docker-compose.production.yml`: the API, a separate queue worker, PostgreSQL, Redis, Caddy TLS, and Prometheus scraping. Create a protected directory containing four files (`beresin_secret_key`, `supervisor_password`, `monitoring_token`, `ai_api_key`), each readable only by the deployment operator. Then set `BERESIN_SECRETS_DIR`, `BERESIN_DOMAIN`, `BERESIN_INIT_SUPERVISOR_EMAIL`, `AI_BASE_URL`, `BERESIN_POSTGRES_PASSWORD`, and `BERESIN_REDIS_PASSWORD`, and run:

```bash
docker compose -f docker-compose.production.yml config
docker compose -f docker-compose.production.yml up --build -d
docker compose -f docker-compose.production.yml ps          # postgres and redis must be healthy
curl --fail https://YOUR_DOMAIN/ready
```

This stack runs the same PostgreSQL + Redis + separate-worker topology that the local pilot and the test suite were verified against. `OPS_AGENTS_ENABLED` is deliberately `false`: the AI Operations agents need the pinned official Hermes runtime, which is not part of the image, and the Coder refuses to run without an OS sandbox (`sandbox-exec` on macOS; Linux hosts need bubblewrap or firejail first). Do not set `OPS_CODER_ALLOW_UNSANDBOXED` on a shared host.

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

For PostgreSQL, the current-database wrapper chooses the correct backend and
creates a SHA-256 sidecar. Restore accepts only a checksum-valid BERESIN archive
and an empty target:

```bash
server/.venv/bin/python ops/backup_current.py
createdb beresin_restore_drill
server/.venv/bin/python ops/restore_postgres.py ~/BeresinBackups/beresin-postgres-TIMESTAMP.dump \
  --database-url postgresql:///beresin_restore_drill --confirm-empty-target
dropdb beresin_restore_drill
```

Run the final wall-clock observation gate with:

```bash
server/.venv/bin/python ops/ai_ops_soak.py --duration-hours 24
```

## Incident response

- AI outage: tasks fail with a user-safe message; inspect failure metrics and upstream status, then retry only idempotent/read operations.
- Agent outage: do not execute against server storage. Restore connectivity, verify the device identity, and allow leased jobs to requeue.
- Suspected device-key exposure: revoke the device in User Settings and pair it again to rotate credentials.
- Unexpected file result: stop the agent, preserve audit/task/job records, and do not retry a destructive action until its snapshot is reviewed again.
- Database issue: stop the API, preserve the database plus WAL/SHM files, validate the latest backup, and restore to a new volume.

## AI Operations Center

The local pilot runs the official Hermes CLI through a private profile under
`server/data/ops-hermes`. The profile stores its provider credential with mode
`0600` and is ignored by Git. Enable it only after this succeeds:

```bash
hermes --version
server/.venv/bin/python ops/incident_drill.py
```

Set `OPS_AGENTS_ENABLED=true` on the server service to enable automatic
read-only Lead, Security, and Diagnostic analysis. Coder is never dispatched
by that loop: it requires a `CODE_FIX` approval and isolated worktree. A
deployment requires a different `DEPLOYMENT` approval plus green recorded
checks.

For Telegram, create a bot with BotFather and configure the following as
protected server secrets. Telegram messages contain only sanitized metadata;
approval remains available only after authenticated Operations Center login.

```text
OPS_TELEGRAM_BOT_TOKEN_FILE=/run/secrets/telegram_bot_token
OPS_TELEGRAM_CHAT_ID=<owner-chat-id>
OPS_PUBLIC_BASE_URL=https://beresin.example.com
```

For CI/security ingestion, add GitHub Actions secrets
`BERESIN_OPS_URL` and `BERESIN_MONITORING_TOKEN`. The Operations Center URL
must be reachable from GitHub-hosted runners. If it is local-only, use a
self-hosted runner or leave ingestion disabled; the workflows safely skip an
unconfigured endpoint.

GitHub branch protection must still be enabled in repository settings when the
account plan supports it. BERESIN enforces its own approval gates regardless,
but it does not claim unavailable GitHub protection is active.

## Rollback

Keep the prior immutable image tag. Stop the new container, back up the current database, and start the prior image only if its schema is backward compatible. Additive migrations in V1 are compatible, but rollback must still be rehearsed against a restored backup.

## Release automation

- `.github/workflows/ci.yml`: backend matrices, agent OS/Python matrices, UI/accessibility, Docker build and Trivy scan.
- `.github/workflows/security.yml`: secret, dependency, configuration and Bandit scans.
- `.github/workflows/release-agent.yml`: builds the terminal-installable Python wheel, verifies installation across supported OS/Python versions, generates checksums, and publishes tagged releases. Native application signing/notarization is intentionally out of scope.
- `ops/release_gate.py`: reproducible local gate report.
