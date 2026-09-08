# Release Checklist — PRD 1–33

Status labels: `PASS` is covered by source plus automated/local verification; `PLATFORM GATE` needs real production infrastructure or OS hardware evidence.

1. Product flow scan → recommend → approve → execute → verify: PASS.
2. Product vision and user/supervisor roles: PASS.
3. Target user boundaries: PASS.
4. Natural-language-first, tool-second behavior: PASS; casual chat tool gating is tested.
5. Shared architecture and separated domain APIs: PASS for single-instance V1.
6. User and supervisor UI, states, structured recommendations, approval cards, progress: PASS; automated desktop/mobile accessibility regression is included.
7. Authentication and RBAC: PASS; password policy, hashed passwords/tokens, expiry, logout revocation, and login throttling covered.
8. Desktop Agent local filesystem execution: PASS; server fallback is prohibited.
9. CLI installation/setup/verify/run: PASS locally. V1 is distributed as a Python wheel installed from the terminal; it is not a desktop application or native installer.
10. Manual/auto startup controls: PASS in source/tests; physical reboot evidence per OS is a PLATFORM GATE.
11. Device registration, health, capabilities, revoke/re-pair: PASS.
12. Agent pipeline and contextual tool gating: PASS.
13. File intelligence parsers/classifier/duplicates/index/search: PASS.
14. Structured organization plans: PASS; plans originate on-device with fingerprints.
15. Incremental indexing, hash cache, local scanning, async tasks: PASS for V1 workload.
16. Tool gateway contracts and device delegation: PASS.
17. Configurable capability/approval policy: PASS; destructive AUTO is forbidden.
18. Approval system: PASS; immutable hash, expiry, ownership, audit, and async execution covered.
19. User memory/context isolation: PASS.
20. Supervisor monitoring/employees/tasks/approvals/activity: PASS.
21. Supervisor natural-language monitoring chat without permission bypass: PASS.
22. Append-only logical audit events: PASS at API level; external immutable log export is a PLATFORM GATE.
23. Persistent task/conversation jobs, status, cancellation, leases and recovery: PASS for one instance.
24. Provider abstraction, tools, retry and streaming: PASS; three consecutive credentialed live contract runs covered streaming and structured tool calling.
25. `/api/auth`, `/api/user`, `/api/supervisor` separation: PASS.
26. Security controls: PASS in application; secret-file injection, TLS topology and CI image/security scans are configured; live TLS and penetration test remain PLATFORM GATES.
27. Concurrent devices and durable SQLite queues: PASS for supported single-instance V1; horizontal multi-instance scaling is out of the supported topology.
28. Structured errors, safe retry, failed task, notifications and audit: PASS.
29. Hash-aware verification and partial-result accounting: PASS.
30. Metrics, device health, AI latency, request IDs, security headers, health/readiness and Prometheus alert rules: PASS; external alert routing is a PLATFORM GATE.
31. V1 must-have scope: PASS subject to the platform gates above.
32. Out-of-scope capabilities were not introduced: PASS.
33. Development phases have implementation artifacts and tests: PASS; Phase 8 production promotion waits on all PLATFORM GATES.

## Mandatory release evidence

- Full backend, agent, and JavaScript checks are green on the release commit.
- Disposable-folder E2E covers scan, structured recommendation, review, approve, move/delete, verification, cancellation, offline device and reconnect.
- macOS and Windows: terminal install, verify, manual start, auto-start, reboot, disable auto-start, reconnect, revoke, re-pair, and upgrade.
- Production-like load: 1,000+ files, two concurrent devices, locked/corrupt/large files, partial batch, provider outage and network interruption.
- TLS and exact CORS origin verified; secrets are injected externally and absent from image/logs.
- Container vulnerability scan and dependency audit have no unaccepted critical/high findings.
- Backup restore drill, rollback drill, metrics ingestion and alerts are evidenced.
- Versioned Python wheel, source archive, and checksums are published through an approved channel; native app signing/notarization is outside the V1 distribution model.
