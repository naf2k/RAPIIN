# BERESIN

BERESIN adalah asisten kerja berbasis percakapan dengan Desktop Agent yang menjalankan operasi file secara lokal, approval sebelum mutasi, verifikasi hasil, isolasi user, dan dashboard supervisor. Spesifikasi produk lengkap ada di [PRD-BERESIN.md](PRD-BERESIN.md).

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

- Frontend statis: `index.html`, `chat.js`, `supervisor/`, dan `user/`.
- Backend: `server/beresin/`; memisahkan `/api/auth`, `/api/user`, `/api/supervisor`, dan `/api/agent`.
- Worker: task conversation berjalan di background thread dan mengirim progress/token melalui SSE.
- Desktop Agent: `agent/beresin_agent/`; hanya menjalankan tool terdaftar dalam workspace yang dikonfigurasi.
- Secret device disimpan di credential vault OS melalui `keyring`, dengan fallback Fernet terikat mesin. File konfigurasi dibatasi ke mode `0600` pada OS POSIX.

## Menjalankan lokal

Persyaratan: Python 3.12+, `uv`, dan provider AI OpenAI-compatible.

```bash
cp server/.env.example server/.env
cd server
uv sync --extra dev
uv run python run.py
```

Buka `http://127.0.0.1:8000`. Frontend disajikan oleh server yang sama sehingga origin API dan UI konsisten.

Di terminal kedua:

```bash
cd agent
uv sync --extra docs --extra dev
uv run beresin-agent setup --server http://127.0.0.1:8000
uv run beresin-agent verify
uv run beresin-agent run
```

Jika entry point belum dipasang, gunakan `uv run python -m beresin_agent.cli ...`. Saat setup, user memilih mode manual atau auto. Mode juga dapat dikelola dengan:

```bash
beresin-agent autostart on
beresin-agent autostart off
beresin-agent autostart
```

## Pengujian

```bash
cd server && uv run pytest -q
cd ../agent && uv run --with pytest pytest -q
node --check ../app.js
node --check ../chat.js
node --check ../supervisor.js
```

Suite mencakup RBAC, approval/resume, isolasi user, queue agent, 1.000+ file, file terkunci, reconnect, toggle autostart, progress count, dan concurrent device.

## Deployment

`docker-compose.yml` menyediakan deployment satu host untuk evaluasi. Sebelum production:

1. Isi environment dari `server/.env.example`; jangan commit token/API key.
2. Pasang reverse proxy TLS dan batasi origin CORS ke domain produksi.
3. Gunakan volume persisten untuk database dan backup terjadwal.
4. Pertahankan satu instance API untuk V1 SQLite. PostgreSQL + broker wajib sebelum menambah replica API.
5. Sambungkan request log, endpoint metrics, health/readiness, dan alert ke stack observability produksi.
6. Distribusikan Desktop Agent sebagai paket bertanda tangan dan gunakan URL HTTPS yang sama saat setup.
7. Uji install, auto-start, reboot, reconnect, revoke, dan upgrade pada setiap OS target sebelum rilis.

Contoh satu-host:

```bash
docker compose up --build -d
docker compose ps
docker compose logs -f beresin
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
