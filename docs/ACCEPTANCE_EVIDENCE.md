# Acceptance Evidence — PRD 35

Evidence date: 2026-09-08. `LOCAL PASS` means automated or runtime evidence exists in this checkout. `EXTERNAL GATE` cannot be honestly passed without release infrastructure, provider credentials, another OS host, or an OS reboot.

| # | Acceptance criterion | Status | Evidence |
|---:|---|---|---|
| 1 | Install Desktop Agent via terminal | LOCAL PASS | Wheel build and clean-environment terminal install; CI verifies the wheel across supported OS/Python versions |
| 2 | Login and register device | LOCAL PASS | API/auth tests and runtime smoke |
| 3 | Select Manual or Auto Start | LOCAL PASS | CLI and startup-mode tests |
| 4 | Auto Start survives PC restart | EXTERNAL GATE | `startup-probe record/verify` now produces real boot-ID evidence; must run on macOS and Windows |
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
| 17 | Mimo can serve as V1 provider | EXTERNAL GATE | The configured `ai-rapiin` alias passed one streaming/tool-call smoke run, but a subsequent live request returned invalid SSE and the alias did not prove the underlying model identity. Require repeated successful runs with provider-reported Mimo V2.5 provenance. |
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
- Live provider contract: one `provider_contract_ok` run was recorded, but stability and Mimo V2.5 provenance remain unproven.

These counts must be regenerated on the release commit; they are not a substitute for CI results or the external gates.
