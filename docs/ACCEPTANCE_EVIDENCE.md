# Acceptance Evidence — PRD 35

Evidence date: 2026-09-08. `LOCAL PASS` means automated or runtime evidence exists in this checkout. `EXTERNAL GATE` cannot be honestly passed without release infrastructure, provider credentials, another OS host, or an OS reboot.

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

- Backend suite: 76 passing tests at the time this document was generated.
- Desktop Agent suite: 30 passing tests at the time this document was generated.
- Browser/accessibility suite: 22 passing checks across desktop and mobile Chromium, including live authenticated pages.
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

Open release blockers:

- The AI provider credential used during diagnostics must be rotated before release, then the provider soak and release gate must be repeated.
- CI and Security passed on the final source commit listed above. A documentation-only evidence commit may follow without changing runtime behavior.

The pilot database now contains exactly two active supervisor accounts as required by PRD section 3. Two obsolete local/test identities were removed after creating the recoverable SQLite backup `server/data/backups/beresin-20260908T115222Z.db`.

These counts must be regenerated on the release commit; they are not a substitute for CI results or the external gates.
