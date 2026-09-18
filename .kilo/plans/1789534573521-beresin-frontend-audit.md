# Audit — BERESIN Frontend (hafgufa) vs PRD

**Tanggal:** 2026-09-16
**Scope audit:** Hanya project ini (UI frontend). Backend, sistem, database berada di project terpisah "BERESIN" dan **tidak** diaudit di sini.
**Keputusan user:** Deliverable = laporan audit saja. Tidak ada rencana implementasi/perubahan kode.

---

## 1. Gambaran Project

| Aspek | Kondisi |
|---|---|
| Stack | Vite 8, React 19, TypeScript 7, Tailwind 3, framer-motion, lucide-react, shadcn-style components |
| Data | 100% mock: hardcoded (`src/supervisor/data.ts`) + `localStorage` (`lib/chat-store.ts`) + timer simulasi |
| API | Tidak ada sama sekali (tidak ada fetch/axios/WebSocket) |
| Routing | Manual via `window.location.pathname` di `src/App.tsx` (tanpa react-router) |
| Build | `npm run build` LULUS (tsc -b + vite build, 1.67s) |
| Test/lint | Tidak ada script test, tidak ada lint |

**Halaman yang ada:**
- `/` — chat user (sidebar, riwayat, quick actions, TaskFlow rekomendasi→approval→progress→result)
- `/onboarding` — 6 langkah: welcome → account → device → verify → startup → done
- `/login` — login supervisor (selalu redirect ke `/supervisor`)
- `/settings`, `/account` — pengaturan & akun user
- `/supervisor[/...]` — Overview, Tasks, Employees, Devices, Approvals, Activity, **Operations**, Settings, Account + Supervisor Chat drawer

---

## 2. Yang Sudah Sesuai PRD (kualitas baik)

- **User chat-first** (§6.4–6.11): sidebar minimal tanpa menu supervisor, empty state, working state, rekomendasi + tombol Apply (§6.8), approval dengan konsekuensi jelas (§6.9), progress bar + count (§6.10), error natural (supervisor side, §6.11)
- **User Settings** (§6.12): Account, Device + status koneksi, Startup toggle, Notifikasi, About — tanpa konfigurasi teknis berlebihan
- **Onboarding** ≈ §9 CLI flow (di-web-kan): login → register device → verify → pilih startup → ready
- **Supervisor**: Overview 3–4 metric card + "Perlu Perhatian" (§6.16), Tasks list + filter + detail timeline (§6.17–6.18), Employees + detail tanpa akses file/chat privat (§6.19), Approvals + panel risiko + confirm destructive (§6.20), Activity timeline bukan raw table (§6.21), Supervisor Chat dengan disclaimer "tidak bypass policy" (§6.22), Account "1 dari 2 kursi" (§7)
- **Visual** (§6.2/6.24): dark theme konsisten, satu accent (violet), merah/kuning/hijau hanya untuk error/warning/success, border subtle, medium radius, tipografi konsisten, status selalu icon+text, click target besar
- **Responsive** (§6.23): table → stacked list di mobile, sidebar collapse, chat composer tetap aksesibel
- **Reduced motion**: `useReducedMotion` + CSS media query dihormati

---

## 3. Non-compliance PRD (prioritas tinggi)

### P1 — Halaman "Operasi" (supervisor) tidak ada di PRD V1
- `src/supervisor/SupervisorPages.tsx:1128` (`OperationsPage`) + nav di `SupervisorApp.tsx:58`
- §6.15: *"Tidak boleh menambahkan menu lain tanpa requirement yang jelas."* Sidebar V1 PRD = Overview, Tasks, Employees, Approvals, Activity, Settings, Account.
- Konten sangat teknis (queue-monitor, Redis, agent roles LEAD/CODER, worktree, freeze) — melanggar §6.28 ("UI seperti monitoring server") untuk supervisor non-teknis.

### P1 — User chat menampilkan internal agent
- `AgentWorkflow`/`ThinkingState` (`components/ui/ai-agent-response.tsx`) dipakai di chat user (`ruixen-moon-chat.tsx:681`) dan menampilkan: nama tool (`read_file`, `edit_file`), kalimat reasoning, terminal command (`beresin verify --planned-task`) + exit code, diff rows.
- §6.6 eksplisit: *"Jangan menampilkan technical logs kepada user"* — contoh yang dilarang persis seperti ini (`ToolCall(...)`, tool names). §6.7: user cukup lihat "● Scanning Downloads...".
- Catatan: `AgentWorkflow` adalah komponen generik berkualitas bagus — cocok untuk internal/ops tool, bukan chat user.

### P2 — 8 quick-action suggestions (chat user)
- `ruixen-moon-chat.tsx:72–84`: 6 primary + 2 secondary = 8 tombol.
- §6.5: maksimal 3–4 contoh prompt.

### P2 — Login tidak branching role
- `LoginPage.tsx:59` selalu `window.location.assign("/supervisor")`.
- §7: minimal role USER dan SUPERVISOR; §25: domain API terpisah. Inkonsistensi demo: onboarding = akun user (Andi), login = supervisor (Raka).

### P3 — Demo keyword-matching
- `createDemoResponse` (`ruixen-moon-chat.tsx:226`) & `answerFor` (`SupervisorApp.tsx:498`) pakai `includes(...)` — bentuk yang dilarang §4.
- **Tolerable** selama murni mock demo, TAPI harus tetap diisolasi dalam satu modul agar mudah diganti dengan panggilan backend/AI asli (project BERESIN). Flag ini penting untuk integrasi nanti.

---

## 4. Bug & Tech Debt

1. **Bug navigasi chat↔settings**: `userView` di `App.tsx:142` hanya membaca `pathname`. Setelah di `/settings` atau `/account`, klik "Chat Baru" (`href="#new-chat"`) tidak kembali ke chat. Link Settings/Akun juga full-page reload.
2. **Mutasi data module-level**: `dispatchTriage` (`SupervisorPages.tsx:1157`) melakukan `incident.assigned.push(...)` pada array `opsIncidents` yang di-import — side effect pada data statis, tidak idempotent antar remount.
3. **Non-null assertion**: `find()!` di `OverviewPage` (`SupervisorPages.tsx:103–104`) — aman untuk data statis saat ini, rapuh jika data berubah.
4. **Branding stale dari template**: `package.json` name = `ruixen-moon-chat-demo`; komponen `RuixenMoonChat`. Bukan masalah fungsional, tapi membingungkan.
5. **Dependency eksternal**: gambar moon dari `cdn.21st.dev` (login + landing chat) — visual rusak offline. PRD mengutamakan kesederhanaan; image lokal lebih aman.
6. **Tidak ada API layer/contracts** — seluruh tipe data inline di `src/supervisor/data.ts` dan `lib/chat-store.ts`. Integrasi dengan backend BERESIN butuh refactor ke service layer + tipe kontrak terpusat.
7. **Tidak ada 404/handle route tak dikenal** — fallback ke `UserApp`.
8. **Tidak ada lint/test script** — tidak ada pengaman regresi.

---

## 5. Rekomendasi (untuk referensi implementasi nanti, tanpa eksekusi)

Urutan prioritas bila user memutuskan memperbaiki:

1. **Hapus/disable halaman Operasi** (nav + page + data ops di `data.ts`) — atau pindahkan ke modul terpisah di luar scope supervisor V1.
2. **Ganti `AgentWorkflow` di chat user** dengan status line sederhana human-friendly ("● Memindai Downloads...", "● Menganalisis 1.248 file...") sesuai §6.7; simpan `ai-agent-response.tsx` untuk kebutuhan internal/teknis di luar UI user.
3. **Kurangi quick actions jadi 3–4** sesuai §6.5.
4. **Login branching**: tentukan role dari akun (mock: `user@` → `/`, `supervisor@` → `/supervisor`), sesuaikan copy halaman login.
5. **Fix bug navigasi** `App.tsx` (state-based view, bukan pathname read), jadikan settings/account sebagai view dalam SPA tanpa reload.
6. **Isolasi mock**: satu modul `lib/mock-backend.ts` (atau `services/`) berisi semua data simulasi + replika kontrak tipe dari API BERESIN, sehingga integrasi = mengganti implementasi tanpa mengubah UI.
7. **Cleanup**: rename package/komponen, lokal-kan gambar, tambah lint + typecheck script.

---

## 6. Validasi audit

- `npm run build` — lulus (tsc strict + vite build)
- Semua file source dibaca: `src/**` (App, Login, Onboarding, Settings, Supervisor App/Pages/data), `components/ui/**` (chat, sidebar, agent-response, task-flow, streaming-text, button, textarea, logo), `lib/**` (chat-store, utils), config (vite, tailwind, tsconfig, index.html, index.css)
- Riwayat git: 1 commit ("Initial commit"), semua file belum di-commit (untracked)

---

## 7. Open questions (opsional, jika audit dilanjutkan ke implementasi)

- Halaman Operasi: dihapus total, atau dipertahankan sebagai fitur opsional di luar PRD V1 dengan approval user?
- Apakah ada data mock yang harus sinkron dengan kontrak API backend BERESIN yang sudah ada (endpoint, field, status enum)? Jika ya, audit lanjutan perlu melihat project backend.
