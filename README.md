# RAPIIN

RAPIIN adalah asisten kerja berbasis percakapan dengan Desktop Agent yang menjalankan operasi file secara lokal, approval sebelum mutasi, verifikasi hasil, isolasi user, dan dashboard supervisor. Spesifikasi produk lengkap ada di [PRD-RAPIIN.md](PRD-RAPIIN.md).

## Arsitektur

```text
Browser user/supervisor
        │ HTTP + authenticated SSE
        ▼
FastAPI API ── Hermes Core ── OpenAI-compatible provider
        │             │
        │             └─ permission → approval → execute → verify
        ▼
SQLite task/job queue
        │ device-scoped polling
        ▼
Desktop Agent ── filesystem user (workspace terbatas)
```

- Backend: `server/rapiin/`; memisahkan `/api/auth`, `/api/user`, `/api/supervisor`, dan `/api/agent`.
- Worker: task conversation berjalan di background thread dan mengirim progress/token melalui SSE.
- Desktop Agent: `agent/rapiin_agent/`; hanya menjalankan tool terdaftar dalam folder yang diizinkan user.
- Frontend (React): `frontend/` dalam repo ini (monorepo) dan bicara ke backend murni via `/api` (same-origin; saat dev, Vite proxy `/api` ke backend).
- Secret device disimpan di credential vault OS melalui `keyring`, dengan fallback Fernet terikat mesin. File konfigurasi dibatasi ke mode `0600` pada OS POSIX.

## Menjalankan lokal

Persyaratan: Python 3.12+, `uv`, dan provider AI OpenAI-compatible.

```bash
cp server/.env.example server/.env
cd server
uv sync --extra dev
uv run python run.py
```

Buka `http://127.0.0.1:8000`. Service ini API-only; frontend React dijalankan
dari `frontend/` (`npm run dev`, proxy `/api` ke backend)
sehingga origin API dan UI konsisten.

Di terminal kedua:

```bash
cd agent
uv sync --extra docs --extra dev
uv run rapiin-agent setup --server http://127.0.0.1:8000
uv run rapiin-agent verify
uv run rapiin-agent run
```

Jika entry point belum dipasang, gunakan `uv run python -m rapiin_agent.cli ...`. Saat setup, user memilih mode manual atau auto. Mode juga dapat dikelola dengan:

```bash
rapiin-agent autostart on
rapiin-agent autostart off
rapiin-agent autostart
```

## Pengujian

```bash
cd server && uv run pytest -q
cd ../agent && uv run --with pytest pytest -q
cd ../frontend && npm run build
```

Suite mencakup RBAC, approval/resume, isolasi user, queue agent, 1.000+ file, file terkunci, reconnect, toggle autostart, progress count, dan concurrent device.

## Deployment

`docker-compose.yml` menyediakan deployment satu host untuk evaluasi. Sebelum production:

1. Isi environment dari `server/.env.example`; jangan commit token/API key.
2. Pasang reverse proxy TLS dan batasi origin CORS ke domain produksi.
3. Gunakan volume persisten untuk database dan backup terjadwal.
4. Pertahankan satu instance API untuk V1 SQLite. PostgreSQL + broker wajib sebelum menambah replica API.
5. Sambungkan request log, endpoint metrics, health/readiness, dan alert ke stack observability produksi.
6. Distribusikan Desktop Agent sebagai wheel rilis dengan checksum terverifikasi dan gunakan URL HTTPS privat yang sama saat setup.
7. Uji install, auto-start, reboot, reconnect, revoke, dan upgrade pada setiap OS target sebelum rilis.

Contoh satu-host:

```bash
docker compose up --build -d
docker compose ps
docker compose logs -f rapiin
```

Untuk produksi multi-instance, queue di source saat ini belum dimaksudkan sebagai pengganti broker durable. Jangan menaruh database SQLite pada shared network filesystem.

Runbook operasi, backup/restore, rollback, dan gate rilis tersedia di [docs/PRODUCTION_RUNBOOK.md](docs/PRODUCTION_RUNBOOK.md) dan [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md).

Evidence tambahan: [acceptance PRD 35](docs/ACCEPTANCE_EVIDENCE.md), [startup test matrix](docs/STARTUP_TEST_MATRIX.md), dan [capacity/scaling decision](docs/CAPACITY_AND_SCALING.md).

## Keamanan operasional

- Mutasi file harus melalui permission engine dan approval sesuai policy.
- Device key disimpan sebagai hash di server dan dapat dicabut user melalui Settings.
- Agent tidak menyediakan arbitrary shell.
- Workspace agent default adalah folder Downloads dan akses di luar workspace ditolak.
- Jangan menaruh password, token, device key, atau connection string di log maupun conversational memory.

Dokumentasi komponen: [server/README.md](server/README.md) dan [agent/README.md](agent/README.md).

Desktop Agent tidak terbatas pada Downloads. Instalasi baru mengizinkan
Downloads, Documents, dan Desktop, sedangkan folder kerja lain dapat ditambah
dengan `rapiin folders add "/path/folder"`. Akses tetap berbasis allowlist;
folder sistem dan kredensial tidak dibuka kepada AI.

Untuk memasang agent pada laptop kedua melalui jaringan privat, ikuti
[runbook laptop kedua](docs/SECOND_DEVICE_RUNBOOK.md). Installer rilis yang
memverifikasi checksum tersedia di `ops/install_rapiin_release.sh`.
