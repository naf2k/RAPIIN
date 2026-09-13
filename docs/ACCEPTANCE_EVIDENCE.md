# Acceptance Evidence — PRD 35

Evidence date: 2026-09-10. `LOCAL PASS` means automated or runtime evidence exists in this checkout. `EXTERNAL GATE` cannot be honestly passed without release infrastructure, another OS host, or a new OS reboot after the current release candidate.

> **Frontend extracted (2026-09-13).** The static frontend (`index.html`, `login.html`, `app.js`, `chat.js`, `supervisor.js`, `styles.css`, `supervisor/`, `user/`, `states/`), the Playwright suite, and the npm tooling no longer live in this repository; they moved to a separate frontend project that consumes this API. Evidence below that names UI, browser, accessibility, frontend-syntax, or npm gates records runs from when the frontend was still in-tree. Those gates are no longer part of this checkout — re-verify them in the frontend project. Backend and Desktop Agent evidence is unaffected. Cross-origin API access for the new frontend is configured through `allowed_origins` in the server settings.

## Multi-device targeting

- Pesan menerima `device_id` milik user dan menolak device milik user lain atau
  device offline.
- Bila lebih dari satu device online, API menolak routing ambigu dan UI meminta
  user memilih target pada kontrol `Kerjakan di`.
- Penerapan rekomendasi selalu kembali ke device pembuat snapshot agar path file
  lokal tidak pernah dialihkan ke komputer lain.
- Bukti otomatis: `server/tests/test_prd_reliability.py`; bukti fisik laptop kedua
  mengikuti `docs/SECOND_DEVICE_RUNBOOK.md`.

| # | Acceptance criterion | Status | Evidence |
|---:|---|---|---|
| 1 | Install Desktop Agent via terminal | LOCAL PASS | Wheel build and clean-environment terminal install; CI verifies the wheel across supported OS/Python versions |
| 2 | Login and register device | LOCAL PASS | API/auth tests and runtime smoke |
| 3 | Select Manual or Auto Start | LOCAL PASS | CLI and startup-mode tests |
| 4 | Auto Start survives PC restart | LOCAL PASS | A real macOS reboot changed the boot identifier; server and agent LaunchAgents restarted with new PIDs, and `startup-probe verify` confirmed connectivity and queue readiness on 2026-09-08. Windows is not part of the selected local-macOS deployment scope. |
| 5 | Natural-language interaction | LOCAL PASS | Fake-provider conversation/E2E tests |
| 6 | Casual conversation does not invoke tools | LOCAL PASS | Deterministic tool gating test |
| 7 | Filesystem task produces understandable plan | LOCAL PASS | On-device structured recommendation snapshot |
| 8 | User approves/rejects | LOCAL PASS | Approval API/UI and E2E tests |
| 9 | Agent executes permitted operations | LOCAL PASS | Local executor and E2E tests |
| 10 | Agent verifies results | LOCAL PASS | Hash/source/destination verification tests |
| 11 | User sees task status | LOCAL PASS | API, SSE and progress UI tests |
| 12 | User memory is isolated | LOCAL PASS | Cross-user authorization tests |
| 13 | User cannot access supervisor capability | LOCAL PASS | RBAC tests |
| 14 | Supervisor monitors user/device/task | LOCAL PASS | Supervisor API/UI tests |
| 15 | Supervisor handles approval by policy | LOCAL PASS | Policy and supervisor approval tests |
| 16 | Important activity is audited | LOCAL PASS | Audit assertions in release E2E |
| 17 | Compatible AI provider serves V1 chat, streaming, and tools | LOCAL PASS | Ten consecutive credentialed conversations passed on 2026-09-08; a live tool call also produced structured file recommendations on the paired device. |
| 18 | Provider can change without Hermes redesign | LOCAL PASS | Provider abstraction and streaming/tool contract tests |
| 19 | Concurrent devices use queue safely | LOCAL PASS | Atomic ownership, lease/requeue/renewal and concurrent-device tests |
| 20 | No unrestricted device access | LOCAL PASS | Agent workspace enforcement for read and mutation tools; traversal/symlink tests |

Current local evidence:

- Backend suite: 122 passing tests on SQLite and 122 passing tests on real PostgreSQL/Redis on 2026-09-10.
- Desktop Agent suite: 38 passing tests on 2026-09-10.
- Browser/accessibility suite: 26 passing checks across desktop and mobile Chromium on 2026-09-10, including owner approval re-authentication.
- Bounded HTTP load probe: 1,000 requests, concurrency 20, zero failures, p50 142.6 ms, p95 239.0 ms, 135.9 requests/second.
- Bandit medium/high scan: pass.
- npm and Python dependency audits: zero known vulnerabilities (the unpublished local `beresin-agent` package itself is not present on PyPI and is therefore skipped by `pip-audit`).
- Terminal wheel exposes both the PRD `beresin` command and the administrative `beresin-agent` alias.
- SQLite WAL backup/restore drill: identical SHA-256 backup and restored database, integrity check `ok`; empty/non-BERESIN databases are rejected.
- Live provider soak: ten consecutive credentialed conversations passed while 220 parallel readiness probes had zero failures. Provider overload, empty stream, and non-stream compatibility responses are covered by retry regression tests.
- Live disposable-folder drill: the on-device agent returned type/year/duplicate recommendation cards; Apply created a user approval; approval queued the mutation back to the same device; 5/5 moves were verified and five physical destination files were independently counted.
- GitHub CI run `34223193132`: pass on commit `6abfe2a8e55e8aada4ede39d626d411eb2c2b7bb`; backend on Python 3.12/3.13, agent tests and wheel builds on Linux/macOS/Windows with Python 3.10/3.13, browser tests, dependency audit, production image build, and high/critical Trivy image scan all passed.
- GitHub Security run `34223193099`: Gitleaks, Trivy filesystem scan, and Bandit medium/high scan passed on the same release commit.
- Local macOS reboot drill: `com.beresin.server` and `com.beresin.agent` started automatically after login; `/ready`, SQLite integrity, device verification, queue readiness, health monitoring, and credentialed AI UAT all passed.
- Local operations drill: restore to a disposable database returned SQLite integrity `ok` with the expected user/task rows; the fresh 1,000-request load probe completed with zero failures and p95 239.0 ms.
- Live AI Operations smoke on 2026-09-10: the enabled background worker automatically dispatched a synthetic read-only incident to Lead, Security, and Diagnostic, then completed Lead synthesis. Four structured reports were persisted, concurrency remained bounded at one, and Hermes token/API-call usage was recorded. The synthetic incidents were resolved after verification.
- PostgreSQL/Redis cutover drill: 31 tables and 5,426 rows migrated under write freeze; live login, agent polling, AI chat, audit verification, worker crash recovery, and readiness passed.
- PostgreSQL disaster-recovery drill: a checksum-protected dump restored into an empty temporary database with expected user and incident counts; the temporary target was removed afterward.
- Fault drills: worker termination raised a critical meta incident and restart auto-resolved it; Telegram failed delivery was retried and sent; three synthetic provider failures opened the circuit and cooldown recovery closed it.
- Coder drill: official pinned Hermes operated only in an isolated worktree, fixed a synthetic negative-delay regression, produced four passing fixture tests plus green backend/agent/JS/diff checks, and the rejected synthetic change was safely cleaned without merge or deployment.
- PostgreSQL lock regression: SSE reads now end their transaction before streaming, periodic monitors no longer run DDL, lock/idle-transaction timeouts are bounded, and an accelerated 36-second soak passed 17/17 samples.
- Final macOS reboot drill: boot identifier changed and server, PostgreSQL, Redis, queue worker, desktop agent, monitor, and backup services all auto-started. The drill exposed and then removed a transient startup false-positive by adding a two-minute Operations heartbeat grace period (two monitor intervals).

Remaining external/final observation gates:

- Complete the 24-hour local soak on the final commit.
- Preserve the verified macOS LaunchAgent definitions when packaging the production host.
- Production deployment still needs its real server/domain, protected GitHub environment, deploy/rollback commands, and organization identity controls.

## Final local verification — 2026-09-10 (post-fix)

Verified directly from source and runtime after the fixes below; supersedes earlier counts where they differ.

- Backend suite: 131 passing tests on SQLite and 131 passing tests on real PostgreSQL/Redis (the 4 earlier PG failures were caused by the test run sharing the pilot Redis queue and are fixed).
- Desktop Agent suite: 38 passing.
- Browser/accessibility suite: 26 passing across desktop and mobile Chromium, including owner approval re-authentication. (Run while the frontend was in-tree; the suite now lives in the frontend project.)
- Release gate (`ops/release_gate.py --topology local-macos`): backend, agent, macOS reboot probe, credentialed UAT, and local health checks all pass. (The frontend-syntax and UI/accessibility gates were removed with the frontend.)
- Operations incident drill (`ops/incident_drill.py`): pass (41 Operations tests, 38 agent tests). (The JS syntax step was removed with the frontend.)
- Provider contract smoke: streaming and tool-calling contracts pass against the configured provider.
- Bounded HTTP load probe: 1,000 requests, concurrency 20, zero failures, p50 556.6 ms, p95 807.5 ms, 34.3 req/s while the Operations AI monitor was active.
- Bandit medium/high scan: pass. pip-audit (server and agent): zero known vulnerabilities. (npm audit no longer applies in this checkout — the npm tooling moved to the frontend project.)
- Readiness CLI (`beresin-ops verify`): all checks green — server, PostgreSQL, roles, audit hash chain, provider circuit closed, assignment queue empty, Redis, pinned Hermes version, Operations enabled, Telegram configured, LaunchAgents loaded, fresh backups.
- Final PostgreSQL backup/restore drill: a checksum-protected dump was created, verified, and restored into an empty throwaway database; user, supervisor, incident, and audit-event counts matched exactly (3 / 2 / 20 / 2826), and the temporary database was dropped afterward.
- Audit hash chain verified valid after every step of this session's cleanup work.

### Fixes applied in this pass

- **Assignment concurrency:** `dispatch_incident` now defers roles when the concurrency limit is held by a stale lease instead of raising `RuntimeError` and aborting the whole monitor tick; queued roles stay `PENDING` and `resume_pending_assignments` continues them on later ticks. Regression test added.
- **Ops CLI entry point:** `python -m beresin.ops_cli verify` no longer exits silently without a report. Regression test added.
- **Redis test isolation:** with `BERESIN_TEST_DATABASE_URL` set, tests now use a dedicated Redis logical database (15). Previously the shared queue key let the live conversation worker consume test jobs and could apply test task ids against the pilot database.
- **Soak integrity:** the soak script now uses a wall-clock deadline and records a `SamplingGap` failure whenever the host suspends sampling, so a sleeping laptop can no longer produce a green 24-hour report.
- **Queue worker resilience:** a single Redis socket timeout used to kill the worker process (observed in the pilot log after a host sleep/wake, exit status 1 followed by a launchd restart). `dequeue_conversation_task` now treats a transient Redis failure as "no work", `enqueue_conversation_task` returns `False` so callers fall back to the in-process thread instead of dropping the task, `redis_ready` reports not-ready instead of raising, and the poll loop logs, backs off, and keeps consuming. The BRPOP socket timeout was also raised above the blocking timeout so an empty queue returns `None` instead of racing its own read deadline. Regression tests added.
- **Notification transaction scope:** `deliver_pending` sent Telegram notifications inside an open database transaction. A blocked Telegram request holds the connection for its full 10-second timeout, and ten queued notifications exceeded PostgreSQL's `idle_in_transaction_session_timeout`, which terminated the connection (`FATAL: terminating connection due to idle-in-transaction timeout`) and aborted the rest of the monitor tick. Pending rows are now read and committed before any network call, each delivery result commits on its own, and `_ops_tick` commits between phases instead of running one tick-wide transaction. Regression test added.
- **Soak startup grace:** the soak shares `RunAtLoad` with the server, so after a reboot it began sampling while the API was still booting and recorded failures that described the boot rather than the run. It now waits (bounded at 300s) for `/ready` before the clock starts, and records `startup_ready` in the report.
- **Coder sandbox fails closed:** the sandbox was applied only when `sandbox-exec` existed, so on any Linux host Hermes ran with full access to the machine instead of being confined to its worktree. A missing sandbox is now a hard failure; `OPS_CODER_ALLOW_UNSANDBOXED` is the explicit, documented opt-in. Regression tests added.
- **Production topology completed:** `docker-compose.production.yml` previously ran the API alone on SQLite with Caddy and Prometheus, which is not the topology any of this evidence was gathered on. It now defines PostgreSQL, Redis, and a separate queue worker alongside the API, with health-gated startup, and the API and worker share the same `BERESIN_DATABASE_URL`/`BERESIN_REDIS_URL` contract as the pilot. `python -m beresin.worker` was added as the standalone worker entry point.

### Drill artifact cleanup

- The third supervisor account left over from the synthetic Coder drill was removed; the pilot has exactly two active supervisor accounts again as required by PRD section 3.
- Drill incidents #5, #6, and #9 were closed, and their drill-only code changes, code approvals, and check runs were removed after the uncommitted drill patch was archived outside the repository (`~/BeresinBackups/drill-artifacts/`). The audit log chain remains valid and intact.
- Drill git worktree `incident-5` and local branches `ops/incident-5` and `ops/incident-9` (which contained no unique commits) were removed.

### Open items

- **The 24-hour soak has not passed and is currently stopped.** Three attempts are recorded: the first was discarded after a host sleep, the second after the host force-slept on a detached charger, and the third after it recorded two `TimeoutError` samples inside monitor-tick stalls (114s and 137s) while the machine was swapping under desktop load. Across attempts the application itself stayed healthy — valid audit chain, no duplicate incidents, no stuck assignments, no worker or database outage — but this 8 GB Mac cannot also act as a daily-driver desktop and hold `/ready` under 5 seconds for 24 uninterrupted hours. A host that exists to be soaked is required.
- The soak is to be re-run on a host that exists to be soaked — the planned staging VPS once `docker-compose.production.yml` is deployed there — so the macOS pilot stops doubling as the soak host. The soak now reports progress every sample (`"status": "running"`) and waits for `/ready` before it starts counting, so both an emerging failure and a reboot are visible instead of silent.
- `pmset -a disablesleep 1` is a temporary drill setting and must be reverted with `sudo pmset -a disablesleep 0` once the soak finally passes.
- Incident #2 (`Disk space critically low`) remains correctly OPEN: the host volume is genuinely below the 10% free threshold used by `ops/local_health_monitor.py`. Resolving it requires the owner to free space on the Mac; BERESIN's own footprint is about 15 MB of data plus backups.

The pilot database now contains exactly two active supervisor accounts as required by PRD section 3. Two obsolete local/test identities were removed after creating the recoverable SQLite backup `server/data/backups/beresin-20260908T115222Z.db`.

These counts must be regenerated on the release commit; they are not a substitute for CI results or the external gates.
