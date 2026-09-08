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
| 17 | Compatible AI provider serves V1 chat, streaming, and tools | LOCAL PASS | Three consecutive live contract runs passed for the configured provider on 2026-09-08; every run covered streaming text and structured tool calling. |
| 18 | Provider can change without Hermes redesign | LOCAL PASS | Provider abstraction and streaming/tool contract tests |
| 19 | Concurrent devices use queue safely | LOCAL PASS | Atomic ownership, lease/requeue/renewal and concurrent-device tests |
| 20 | No unrestricted device access | LOCAL PASS | Agent workspace enforcement for read and mutation tools; traversal/symlink tests |

Current local evidence:

- Backend suite: 66 passing tests at the time this document was generated.
- Desktop Agent suite: 29 passing tests at the time this document was generated.
- Browser/accessibility suite: 22 passing checks across desktop and mobile Chromium, including live authenticated pages.
- Bounded HTTP load probe: 500 requests, concurrency 20, zero failures, p50 80.1 ms, p95 222.3 ms, 188.9 requests/second.
- Bandit medium/high scan: pass.
- npm dependency audit: zero known vulnerabilities.
- Terminal wheel exposes both the PRD `beresin` command and the administrative `beresin-agent` alias.
- SQLite WAL backup/restore drill: identical SHA-256 backup and restored database, integrity check `ok`; empty/non-BERESIN databases are rejected.
- Live provider contract soak: three consecutive `provider_contract_ok` runs for streaming text and structured tool calling.
- GitHub CI run `34185814826`: pass on commit `9f77e139d58b8e249fc86fe8471188cbd340cd79`; backend on Python 3.12/3.13, agent tests and wheel builds on Linux/macOS/Windows with Python 3.10/3.13, browser tests, dependency audit, production image build, and high/critical Trivy image scan all passed.
- GitHub Security run `34185814824`: Gitleaks, Trivy filesystem scan, and Bandit medium/high scan passed on the same release candidate line.
- Local macOS reboot drill: `com.beresin.server` and `com.beresin.agent` started automatically after login; `/ready`, SQLite integrity, device verification, queue readiness, health monitoring, and credentialed AI UAT all passed.
- Local operations drill: daily LaunchAgent backup completed; restore to a disposable database returned `ok` and an identical SHA-256; 1,000-request load probe completed with zero failures and p95 170.2 ms.

These counts must be regenerated on the release commit; they are not a substitute for CI results or the external gates.
