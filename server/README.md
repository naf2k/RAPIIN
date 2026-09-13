# BERESIN Server

Backend BERESIN V1 - Hermes Core (engine agent Python/FastAPI) + frontend terintegrasi.
Server menyajikan API (`/api/*`) sekaligus frontend statis di root repo.

## Prasyarat

- `uv` terinstal
- Router AI lokal aktif (9router) di `http://localhost:20128/v1` (atau OpenAI-compatible lain)

## Setup development

```bash
cd server
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
cp .env.example .env   # lalu isi AI_API_KEY sesuai router Anda
```

`.env` berisi:
- `AI_BASE_URL` / `AI_API_KEY` / `AI_MODEL` untuk provider AI (V1: 9router)
- `BERESIN_INIT_SUPERVISOR_EMAIL` / `BERESIN_INIT_SUPERVISOR_PASSWORD` untuk akun supervisor awal
- `BERESIN_DB_PATH` lokasi database SQLite

## Menjalankan (development)

```bash
cd server
.venv/bin/python run.py
```

Server berjalan di `http://127.0.0.1:8000`. Hanya API yang disajikan di sini; dokumentasi API di `/docs`, dan pemeriksaan runtime di `/health` serta `/ready`.

## Menjalankan (production, Docker)

```bash
cp .env.example .env
docker compose up --build -d
```

Atau tanpa Docker:

```bash
cd server
BERESIN_ENV=production .venv/bin/python run.py
```

## Akun awal

- Supervisor: `supervisor@beresin.example.com` / `Supervisor123!` (di-seed otomatis saat pertama kali server berjalan)
- User: daftar melalui `POST /api/auth/register` atau via UI login

## Endpoint utama

- `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/heartbeat`
- `POST /api/user/conversations`
- `POST /api/user/conversations/{id}/messages` (alur Hermes Core + tool calling)
- `GET /api/user/tasks`, `GET /api/user/approvals`
- `POST /api/user/approvals/{id}/respond`
- `GET /api/supervisor/overview`, `GET /api/supervisor/tasks`, `GET /api/supervisor/employees`
- `GET /api/supervisor/approvals`, `POST /api/supervisor/approvals/{id}/respond`
- `GET /api/supervisor/activity`, `POST /api/supervisor/chat`

## Struktur

```text
server/
├── beresin/
│   ├── ai/           # provider AI (OpenAI-compatible, retry + SSE parsing)
│   ├── agent/        # Hermes Core loop + prompts
│   ├── tools/        # Tool Gateway, filesystem, parser, duplicate, verify, analysis
│   ├── api/          # auth, user, supervisor routes
│   ├── permissions.py
│   ├── approval.py   # approval + resume eksekusi setelah approve
│   ├── tasks.py
│   ├── devices.py    # heartbeat + monitor offline berkala
│   ├── memory.py
│   └── audit.py
├── tests/
├── run.py
└── pyproject.toml
```

## Fitur V1 yang diimplementasikan

- Tool calling via provider AI (scan, search, metadata, duplicate, document parser,
  classifier, semantic indexer, move/copy/rename/delete/batch).
- Verifikasi hasil operasi di filesystem (move/copy/delete/rename) sebelum task
  dianggap sukses (PRD section 29).
- Approval user/supervisor; saat disetujui operasi yang tertunda langsung dieksekusi
  dan diverifikasi (PRD section 18).
- Parser modular: PDF, DOCX, XLSX, PPTX, TXT, CSV, JSON, ZIP, metadata gambar.
- Device Manager dengan heartbeat; server menandai device offline otomatis tiap 30 detik.
- **Desktop Agent delegation**: tool read/analisis (scan, search, duplicate, parser,
  classifier, indexer) otomatis didelegasikan ke Desktop Agent yang terpasang di
  komputer user via antrean job (`/api/agent/poll`, `/api/agent/result`). Jika device
  agent offline, server memakai fallback sandbox lokal. Lihat `../agent/README.md`.
- Audit log append-only; RBAC; isolasi memory per user; sandbox filesystem.
- Frontend (login, chat user, supervisor) disajikan server dan terhubung penuh ke API.

## Test

```bash
cd server
.venv/bin/python -m pytest tests/ -q
```

## Catatan

- File yang diakses agent dibatasi pada sandbox root (default folder Downloads atau `BERESIN_SANDBOX_ROOT`).
- Operasi destruktif tidak dijalankan tanpa persetujuan (user/supervisor).
- Audit log bersifat append-only dan tidak dapat diubah user biasa.
