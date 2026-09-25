# LAPORAN PROGRES — RAPIIN (di-rename dari BERESIN pada 18 Sep 2026)

**Tanggal:** 18 September 2026
**Status keseluruhan:** ~90% tahap pilot/demo. Fondasi + aplikasi + uji Windows selesai. Sisa: kuota AI (demo live), integrasi server kantor Ubuntu, penguatan skala 50+ karyawan.
**Dokumen acuan:** `PRD.md` (spesifikasi produk, repo ini).

> Catatan keamanan: dokumen ini TIDAK memuat password, token, API key, atau device key.
> Semua rahasia hanya ada di `server/.env` (Mac pilot, mode 0600, gitignored) dan nanti di
> `RAPIIN_SECRETS_DIR` pada server produksi.

---

## 1. Ringkasan eksekutif

RAPIIN adalah AI work assistant: karyawan ngomong bahasa natural → sistem memahami,  
merencanakan, minta approval bila perlu, mengerjakan file di PC karyawan, verifikasi hasil,  
lalu menjelaskan hasilnya. Supervisor memonitor semuanya dari dashboard.


| Area                                             | Status                         | Bukti                                                  |
| ------------------------------------------------ | ------------------------------ | ------------------------------------------------------ |
| Backend (Core API + Hermes + Task Engine)        | ✅ Selesai                      | 159 tes server hijau                                   |
| Desktop Agent Windows (CLI `rapiin`)            | ✅ Selesai                      | 38 tes agent hijau + matrix Windows 10/10 lulus        |
| Frontend React `hafgufa` (chat + supervisor)     | ✅ Selesai                      | Build sukses, wiring login/overview/RBAC terbukti live |
| Instalasi 1-klik Windows (`Install-Rapiin.ps1`) | ✅ Selesai                      | Terbukti dipakai instalasi nyata 18 Sep 2026           |
| Demo chat AI live E2E                            | ⏳ Nunggu kuota AI              | Kontrak endpoint cocok, tes fake-provider hijau        |
| Server kantor Ubuntu 24/7                        | ⏳ Masi menunggu                | Spek + 5 perintah cek sudah disiapkan                  |
| Skala 50+ karyawan konkuren                      | ⏳ Desain siap, belum load-test | Topologi produksi ada, bottleneck terpetakan           |


---

## 2. Arsitektur &amp; cara kerja

### 2.1 Gambar besar

```text
Browser karyawan/supervisor (hafgufa React)
        │ HTTPS + token + SSE
        ▼
FastAPI API ── Hermes Core ── AI provider (OpenAI-compatible; hangat: hosted, wajib: lokal)
   │    │            │
   │    │            └─ permission → approval → execute → verify
   │    ▼
   │  SQLite (pilot) / Postgres+Redis (produksi) + task queue
   │         │ device-scoped polling (tiap 3 detik)
   ▼         ▼
Desktop Agent di tiap PC ── filesystem karyawan (folder yang diizinkan)
```

Prinsip: **satu Core Backend sebagai sumber kebenaran**, User API dan Supervisor API
dipisah (`/api/auth/*`, `/api/user/*`, `/api/supervisor/*`, `/api/agent/*`), scan file tetap
**lokal di PC** (isi file mentah tidak dikirim ke server — hanya metadata/hasil analisis).

### 2.2 Alur chat karyawan 

```text
Pesan user → Konteks percakapan → Hermes → Paham maksud
  → Perlu aksi? TIDAK → jawab natural (tanpa tool)
  → YA → Rencana → Pilih tool → Cek izin → Perlu approval?
      → YA → user/supervisor approve → Eksekusi di device → Verifikasi (hash/sumber/tujuan)
      → TIDAK → Eksekusi → Verifikasi
  → Update konteks → Jawab natural + kartu rekomendasi/progress
```

### 2.3 Alur device 

```text
Install (wheel/script 1-klik) → rapiin setup (login + register device + pilih manual/auto)
  → rapiin verify → poll tiap 3 dtk (heartbeat + ambil job + baca startup_mode)
  → autostart: macOS LaunchAgent / systemd / folder Startup Windows
  → reboot → hidup sendiri → reconnect otomatis (backoff maks 60 dtk)
```

Perintah agent: `setup, run, status, verify, autostart on|off, logout, upgrade --wheel, uninstall, startup-probe record|verify, folders list|add|remove`.  
Perintah `rapiin` tanpa argumen: kalau belum setup → first-run setup; kalau sudah → `run`.

### 2.4 Alur supervisor 

Overview (status, user aktif, task jalan, success rate, needs attention) → Employees →
Devices → Tasks (+detail progress/activity) → Approvals (approve/reject) → Activity
(timeline audit) → Supervisor Chat (tanya natural dari data monitoring, tanpa bypass izin).

### 2.5 Memori &amp; isolasi 

- Ingatan per `user_id` (`UNIQUE(user_id,kind,key)`); riwayat chat per conversation milik user.
- Semua query user filter `user_id`; akses silang → 404 (dibuktikan `test_isolation.py`).
- Password/token/API key **ditolak** masuk memori (422) + disensor `[REDACTED]` di riwayat AI.
- Supervisor **tidak punya endpoint** baca isi chat/memori user (hanya metadata operasional).
- Risiko sisa (dicatat, ditutup sebelum produksi besar): `device_key` belum disensor,
1 helper tanpa cek `user_id` (aman lewat caller), memori tanpa TTL/ringkasan.

---

## 3. Stack yang dipakai

### 3.1 Backend — `projects/RAPIIN/server/` (canonical)


| Lapisan           | Teknologi                                                                                                                                                                                                                                               |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Bahasa/runtime    | Python 3.13 (`python:3.13-alpine` di Docker)                                                                                                                                                                                                            |
| Framework API     | FastAPI + SSE (`text/event-stream`) untuk progress/token                                                                                                                                                                                                |
| Auth              | Token Bearer (TTL 7 hari), hashing password, throttling login 5x/15 mnt, RBAC `USER`/`SUPERVISOR` (maks 2 supervisor, enforce app-level)                                                                                                                |
| Database          | SQLite WAL (pilot) → PostgreSQL 17 (produksi); migrasi via `ops/migrate_sqlite_to_postgres.py`                                                                                                                                                          |
| Antrean           | SQLite sebagai source of truth + Redis (LPUSH/BRPOP, pub/sub event) di produksi; worker terpisah `python -m rapiin.worker`                                                                                                                             |
| AI                | `OpenAICompatibleProvider` (chat, tool calling, structured output, streaming SSE, retry 429/5xx, timeout 120 dtk, maks 12 iterasi). `LocalProvider` = future — model lokal dipakai via endpoint OpenAI-compatible (vLLM/Ollama), tanpa ubah Hermes Core |
| Audit             | Append-only + hash chain (`verify_audit_chain`), export ≤5000/limit                                                                                                                                                                                     |
| File intelligence | Parser PDF/DOCX/XLSX/PPTX/TXT/CSV/gambar, hash SHA-256 + cache, deteksi duplikat, klasifikasi, index inkremental                                                                                                                                        |
| Secret            | File env + `_FILE` (Docker secrets), mode 0600, tidak pernah di-log                                                                                                                                                                                     |


### 3.2 Desktop Agent — `projects/RAPIIN/agent/`


| Lapisan        | Teknologi                                                                                                                                    |
| -------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| Bahasa/runtime | Python ≥3.10, dipaket sebagai wheel (`rapiin-agent`)                                                                                         |
| Install        | `uv tool install <wheel>` (atau `pipx`); entry points `rapiin` + `rapiin-agent`                                                              |
| Kredensial     | OS credential vault via `keyring`, fallback Fernet terikat mesin; config `~/.rapiin/` (POSIX) / `%LOCALAPPDATA%\RAPIIN\` (Windows)          |
| Guard          | Allowlist folder (default Downloads/Documents/Desktop, bisa tambah), blokir path sistem/kunci, tolak Downgeluar workspace, tanpa shell bebas |
| Distribusi     | GitHub Release privat (`agent-v*`) + `ops/install_agent_release.sh` (Linux/Mac) + `ops/Install-Rapiin.ps1` (Windows 1-klik)                 |


### 3.3 Frontend — `workspaces/rapiin/` (React, aktif)


| Lapisan   | Teknologi                                                                                                                                  |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Framework | React 19 + TypeScript + Vite 8 (dev proxy `/api` → backend)                                                                                |
| UI        | TailwindCSS 3, Radix Slot, framer-motion, lucide-react                                                                                     |
| Data      | `fetch` + Bearer token (`lib/api.ts`), SSE via fetch (`lib/sse.ts`), session di `localStorage`                                             |
| Halaman   | Chat-first user (history, approval card, progress, settings/startup) + Supervisor console + onboarding 6 langkah + panduan install Windows |
| Build     | `tsc -b && vite build` → `dist/` (disajikan untuk tes via proxy statis + Tailscale)                                                        |


### 3.4 Infra &amp; operasi (pilot → produksi)


| Kebutuhan  | Pilot (sekarang)                                                                                                        | Produksi (server kantor Ubuntu 24/7)                 |
| ---------- | ----------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| Host       | Mac laptop + Tailscale Serve                                                                                            | Ubuntu LTS + Docker + Compose                        |
| URL        | `https://<mac>.ts.net` (+`:8443` dashboard)                                                                             | `https://<domain-LAN>` via Caddy (TLS)               |
| DB/queue   | SQLite + thread inline                                                                                                  | Postgres 17 + Redis 7 (appendonly) + worker terpisah |
| Monitoring | Health monitor lokal                                                                                                    | Prometheus + alerts (+receiver menyusul)             |
| Backup     | Manual (`backup_current.py` + SHA-256)                                                                                  | Terjadwal + retensi ≥30 hari + drill restore         |
| CI         | GitHub Actions: backend py3.12/3.13, agent Linux/macOS/Windows py3.10–3.13, browser, audit dep, Trivy, Gitleaks, Bandit | Sama + release gate per commit rilis                 |


---

## 4. Progres 


| Fase PRD                                                      | Status     | Catatan                                                                                          |
| ------------------------------------------------------------- | ---------- | ------------------------------------------------------------------------------------------------ |
| 1 Foundation (repo, backend, auth, AI abstraction, API)       | ✅          | 159 tes; provider abstraction tanpa hardcode                                                     |
| 2 Desktop Agent (CLI, register, heartbeat, autostart)         | ✅          | 38 tes; matrix Windows 10/10 (lihat §6)                                                          |
| 3 File Intelligence (scan, parser, hash, duplikat)            | ✅          | Parser modular; cache hash; batas 5000 file/scan                                                 |
| 4 Agent Execution (gateway, permission, approval, verifikasi) | ✅          | Policy AUTO/USER/SUPERVISOR; verifikasi hash                                                     |
| 5 User UI (chat, approval UI, progress, settings)             | ✅          | Chat-first; panduan install Windows ditambahkan                                                  |
| 6 Supervisor (auth, overview–activity, chat)                  | ✅          | 2 akun; chat monitoring tanpa bypass izin                                                        |
| 7 Testing                                                     | ✅ Sebagian | Unit/integrasi/RBAC/isolasi/reliability hijau; **kurang**: load test chat konkuren + soak 24 jam |
| 8 Deployment                                                  | ⏳          | Pilot jalan; produksi (server Ubuntu) + distribusi massal npm menyusul                           |


### Acceptance — status pilot

**20/20 LOCAL PASS** di checkout kanonis (evidence `docs/ACCEPTANCE_EVIDENCE.md` 10 Sep 2026;
gates eksternal: soak 24 jam + deploy produksi + reboot Windows kini sudah dilengkapi
bukti Windows 18 Sep 2026, lihat §6). Acceptance diulang penuh di commit rilis server produksi.

---

## 5. Struktur repo (monorepo RAPIIN)

```text
~/orca/projects/rapiin/          ← KANONIS (satu repo): server/ + agent/ + frontend/ + ops/ + deploy/ + docs/
~/orca/workspaces/BERESIN/ui/    ← Legacy: UI vanilla dibekukan + arsip backend 17 Sep 2026
~/Documents/rapiin-windows-test/ ← Paket tes Windows (script+wheel+SHA256SUMS+petunjuk)
```

Frontend React (`frontend/`, dulu repo terpisah `hafgufa`) digabung ke monorepo
dengan riwayat commit dipertahankan.

Commit penting: backend `060129a` (port fixes + filter `.git`), hafgufa `e883397` (React full)

- `e3c6a9b` (hapus tombol kembali login). File baru belum commit: `ops/Install-Rapiin.ps1`
(+fix PATH/WheelDir) — ikut commit rename RAPIIN.

---

## 6. Hasil uji Windows 18 Sep 2026 (10/10 LULUS)

Device `DESKTOP-B5G5UDL-WIN` (Windows 11), server di Mac via Tailscale, akun tes
(dinonaktifkan setelah tes — pilot bersih kembali).


| #   | Tes                                                  | Hasil |
| --- | ---------------------------------------------------- | ----- |
| 1   | Install bersih + cek checksum                        | ✅     |
| 2   | Pair + verify (id 4, ONLINE)                         | ✅     |
| 3   | Manual (`run` hanya saat dibuka)                     | ✅     |
| 4   | Auto (Startup folder terpasang)                      | ✅     |
| 5   | Reboot (boot baru + nyala sendiri + verify OK)       | ✅     |
| 6   | Disable (reboot → tetap mati)                        | ✅     |
| 7   | Reconnect (WiFi mati 60 dtk → pulih, tanpa dobel)    | ✅     |
| 8   | Revoke (kunci lama ditolak) + re-pair (id 5, ONLINE) | ✅     |
| 9   | Upgrade (config utuh, verify OK)                     | ✅     |
| 10  | Uninstall (bersih total)                             | ✅     |


Temuan diperbaiki saat itu juga: script install daftarkan `rapiin` ke PATH otomatis +
tahan bila folder script tak kedetek (`$PSScriptRoot` kosong).

---

## 7. Yang belum + rencana (sesuai keputusan)

1. **Kuota AI (minggu ini)** → `provider_smoke` hijau → 1 chat E2E live penuh pertama.
2. **Demo + 1 karyawan** → install &lt;15 mnt, chat→approve→verifikasi, supervisor memantau.
3. **Server kantor Ubuntu 24/7** → kirim hasil `uname -a; nvidia-smi; free -h; df -h; ip a`;
 migrasi DB, cutover device (setup ulang per PC), pensiunkan Mac sebagai server.
4. **LLM lokal wajib** → runtime (vLLM/Ollama) + model tool-calling lolos smoke test; data tetap di gedung.
5. **Rename RAPIIN full tanpa alias** (±3–4 hari, 6 fase) — termurah dilakukan SEBELUM produksi.
6. **Skala 50+**: batasi thread worker + circuit breaker chat, load test 10→20→30 chat bareng,
 password kuat + refresh token + revoke-all admin, retensi audit, npm massal (`npm i -g`),
 Alertmanager, soak 24 jam + acceptance final di server kantor.

## 8. Keputusan yang sudah dikunci

- Scale target **50+ karyawan** (~30 chat bareng) — single server + Postgres/Redis cukup; replika di luar V1.
- LLM **lokal wajib** (privasi); hosted hanya untuk buktiin chat minggu ini.
- Distribusi produksi via **npm** (`npm install -g`), paket publik berisi installer+exe (tanpa rahasia).
- Tanpa VPS (kecuali opsional gladi soak); produksi = server kantor. Tailscale bisa dilepas bila satu LAN.
- Server OS: **Ubuntu LTS**. UI vanilla lama: **dibekukan**.

## 9. Cara menjalankan (ringkas)

```bash
# Backend (Mac pilot)
cd ~/orca/projects/RAPIIN/server && uv sync --extra dev && uv run python run.py  # :8000

# Agent (PC karyawan, via script 1-klik, atau manual)
uv tool install rapiin_agent-1.0.0-py3-none-any.whl
rapiin setup --server https://SERVER --workspace "$HOME/Downloads" --autostart
rapiin verify && rapiin run   # atau mengandalkan autostart

# Frontend (dev)
cd ~/orca/workspaces/rapiin/ && RAPIIN_API_URL=http://127.0.0.1:8000 npm run dev  # :5174

# Tes
cd server && uv run pytest -q            # 159 lolos
cd ../agent && uv run --with pytest pytest -q  # 38 lolos
```

---

