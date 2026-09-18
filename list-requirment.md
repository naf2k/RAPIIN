Berikut daftar pekerjaan sampai RAPIIN benar-benar layak produksi sesuai PRD. Saya pisahkan antara blocker rilis, kelengkapan produk, testing, dan operasional.
## P0 — Blocker produksi

### 1. Perbaiki arsitektur multi-device

- Jangan menandai device lama `OFFLINE` ketika user mendaftarkan device baru.
- Izinkan beberapa device milik satu user online bersamaan.
- Tambahkan pemilihan device saat user memiliki lebih dari satu device.
- Pastikan job hanya dapat diklaim device tujuan.
- Cegah satu job diklaim dua agent secara bersamaan.
- Tambahkan recovery untuk job `CLAIMED` ketika agent mati atau timeout.
- Test concurrent polling beberapa device milik user yang sama.

### 2. Buat Desktop Agent benar-benar bisa di-install

- Tambahkan build system Python yang benar.
- Pastikan entry point `rapiin-agent` ikut terpasang.
- Build wheel/package agent.
- Uji instalasi pada environment kosong.
- Pastikan perintah berikut bekerja setelah install:
  - `rapiin-agent setup`
  - `rapiin-agent run`
  - `rapiin-agent status`
  - `rapiin-agent verify`
  - `rapiin-agent autostart on`
  - `rapiin-agent autostart off`
  - `rapiin-agent logout`
- Tentukan mekanisme distribusi dan update agent.
- Tanda tangani package/binary untuk macOS dan Windows.
- Tambahkan version compatibility antara agent dan server.

### 3. Hubungkan Startup Settings web dengan agent lokal

- Perubahan mode dari halaman Settings harus diterima agent.
- Agent harus mengaktifkan atau menonaktifkan startup OS sesuai perubahan.
- Tampilkan status aktual startup service, bukan hanya nilai database.
- Tampilkan error jika perubahan gagal.
- Sinkronkan kembali status setelah restart.
- Audit setiap perubahan startup.
- Pastikan device offline tidak ditampilkan seolah perubahan berhasil.

### 4. Gunakan durable task queue

Background thread FastAPI dan queue SQLite belum cukup untuk produksi.

- Gunakan broker/queue durable, misalnya Redis + worker atau alternatif setara.
- Pisahkan API process dan worker process.
- Simpan status task secara persisten.
- Tambahkan lease/visibility timeout untuk job.
- Kembalikan job ke antrean jika agent atau worker mati.
- Tambahkan idempotency agar mutasi tidak dijalankan dua kali.
- Tambahkan retry dengan batas dan backoff.
- Tambahkan dead-letter queue.
- Pulihkan task setelah server restart.
- Pastikan beberapa worker dapat berjalan bersamaan.
- Ganti event streaming in-memory dengan mekanisme lintas-instance.

### 5. Migrasi database produksi

- Gunakan PostgreSQL untuk deployment produksi.
- Tambahkan migration framework/versioned migrations.
- Tambahkan connection pooling.
- Definisikan transaction boundary untuk approval, claim, execute, dan result.
- Tambahkan unique constraint dan index yang diperlukan.
- Audit foreign-key cascade saat revoke device/user.
- Tambahkan backup otomatis.
- Uji restore backup.
- Definisikan retention untuk audit, task, notification, dan conversation.

### 6. Tegakkan HTTPS/TLS

- Semua koneksi production wajib HTTPS.
- Agent menolak HTTP pada environment production.
- Konfigurasikan certificate validation.
- Jangan menyediakan opsi insecure tanpa development flag.
- Batasi CORS ke origin production.
- Tambahkan trusted host/proxy configuration.
- Amankan header HTTP: HSTS, CSP, frame policy, content-type policy.
- Uji koneksi agent melalui reverse proxy TLS.

### 7. Selesaikan keamanan autentikasi

- Ganti default development secret dan supervisor password.
- Server harus menolak startup production jika secret/default password belum diganti.
- Tambahkan rate limit login, register, chat, approval, dan device polling.
- Tambahkan lockout/throttling percobaan login.
- Rotasi session token setelah login sensitif.
- Sediakan expiry dan refresh/re-authentication yang jelas.
- Revoke semua token setelah perubahan password jika diperlukan.
- Batasi jumlah sesi aktif.
- Tambahkan CSRF strategy bila autentikasi kemudian memakai cookie.
- Pastikan password tidak pernah masuk log/audit.
- Tambahkan security audit dependency.

## P1 — Kelengkapan fitur Must Have V1

### 8. Device identity dan monitoring lengkap

- Agent mengirim capabilities saat registrasi.
- Simpan dan tampilkan current task per device.
- Hitung connection health, bukan hanya `ONLINE/OFFLINE`.
- Tampilkan agent version dan status kompatibilitas.
- Tampilkan waktu heartbeat terakhir.
- Tampilkan alasan offline atau degraded.
- Tambahkan rotate device key.
- Pastikan revoke menghentikan agent mengambil job berikutnya.
- Beri notifikasi bila agent perlu diperbarui.

### 9. Policy management supervisor

Saat ini policy masih hardcoded.

- Buat model policy persisten.
- Tambahkan UI supervisor untuk membaca dan mengubah policy.
- Konfigurasikan approval berdasarkan:
  - jenis operasi;
  - jumlah file;
  - scope folder;
  - level risiko;
  - user/device tertentu.
- Bedakan user approval dan supervisor approval.
- Validasi policy server-side.
- Versioning perubahan policy.
- Catat perubahan policy di audit.
- Tambahkan default policy yang aman.
- Cegah policy mengizinkan protected paths atau arbitrary shell.

### 10. Tool Gateway sesuai kontrak PRD

- Ekspos `pdf_parser`.
- Ekspos `spreadsheet_parser`.
- Ekspos `verification`.
- Pastikan semua tool mempunyai structured input/output.
- Tolak tool yang tidak dikenal.
- Validasi seluruh path sebelum job dikirim ke device.
- Validasi kembali path di Desktop Agent.
- Tambahkan timeout per tool.
- Tambahkan limit jumlah dan ukuran file.
- Normalisasi error menjadi pesan natural.
- Pastikan seluruh mutasi menghasilkan:
  - `planned_count`;
  - `executed_count`;
  - `verified_count`;
  - `failed_count`.

### 11. File intelligence lengkap

- Pastikan scanner dapat menangani ribuan file tanpa memuat semuanya ke memori.
- Tambahkan pagination/chunking hasil.
- Implementasikan incremental index di Desktop Agent.
- Tambahkan hash cache.
- Tambahkan extraction cache.
- Proses ulang hanya file baru atau berubah.
- Hapus index file yang sudah tidak ada.
- Tambahkan cache schema/version migration.
- Batasi ukuran extracted text.
- Pastikan raw file tidak dikirim ke server.
- Tambahkan parallel processing untuk operasi read-only yang aman.
- Tambahkan batch processing dengan batas concurrency.
- Tangani symlink dan loop direktori.
- Tangani file berubah saat sedang dipindai.
- Tangani filename/path Unicode dan sangat panjang.

### 12. Parser file V1

Validasi format sesuai PRD:

- PDF.
- DOC/DOCX.
- XLS/XLSX.
- PPT/PPTX.
- TXT.
- CSV.
- Common image metadata.
- ZIP metadata.
- Folder metadata.

Untuk setiap format:

- file valid;
- file kosong;
- file besar;
- file rusak;
- file terenkripsi/password protected;
- file terkunci;
- permission denied;
- parser dependency tidak tersedia;
- hasil error natural tanpa stack trace.

### 13. Alur organisasi file end-to-end

- Scan berjalan di Desktop Agent.
- Metadata dan hash dihitung lokal.
- Duplicate detection berjalan lokal.
- Classification menghasilkan rekomendasi terstruktur.
- Rekomendasi menampilkan jumlah dan contoh file.
- Review menampilkan perubahan sebelum eksekusi.
- Approval menghasilkan snapshot plan yang immutable.
- Eksekusi memakai snapshot yang sudah disetujui.
- Perubahan file setelah approval harus dideteksi.
- Verifikasi dilakukan setelah setiap operasi.
- Partial failure dilaporkan per file.
- Hasil akhir menyebut jumlah sukses dan gagal.
- Retry hanya dilakukan untuk operasi yang aman.
- Tidak ada fallback diam-diam ke filesystem server ketika target seharusnya device user.

Poin terakhir sangat penting: jika agent offline, task seharusnya menunggu atau gagal dengan jelas—bukan menjalankan operasi pada sandbox server seolah itu komputer user.

### 14. Task lifecycle lengkap

- Implementasikan semua status PRD secara konsisten.
- Tambahkan endpoint dan UI pembatalan task.
- Worker mendukung cooperative cancellation.
- Tambahkan timeout task.
- Tambahkan retry status dan attempt count.
- Simpan current step.
- Simpan processed/total count.
- Simpan error code terstruktur.
- Simpan hasil partial.
- Jangan tandai sukses sebelum verifikasi selesai.
- Pastikan task approval dapat dilanjutkan setelah restart server.
- Cegah task selesai dua kali.
- Tambahkan idempotency key untuk permintaan user.

### 15. Streaming production-ready

- Tangani disconnect dan reconnect SSE.
- Tambahkan event ID/resume cursor.
- Hindari kehilangan event saat pindah instance.
- Batasi subscriber per user/task.
- Hentikan stream saat task terminal.
- Tangani provider yang tidak mendukung streaming.
- Tangani tool-call chunks yang terfragmentasi.
- Jangan tampilkan jawaban streaming ganda ketika polling selesai.
- Tambahkan timeout dan cancellation provider.
- Uji streaming melalui reverse proxy production.

### 16. Supervisor lengkap

- Supervisor dapat melihat seluruh device yang relevan.
- Device detail memiliki current task dan health.
- Task detail menampilkan progress, error, hasil, dan audit.
- Approval review menampilkan daftar perubahan secara aman.
- Supervisor dapat menangani approval tanpa melihat private chat.
- Activity mempunyai pagination dan filter.
- Overview memakai data aktual.
- Supervisor Chat menjawab dari data authorized.
- Supervisor Chat tidak dapat memanggil capability user.
- Sediakan maksimal dua akun supervisor secara nyata.
- Tambahkan flow membuat/mengundang supervisor kedua.
- Tegakkan limit dua supervisor di backend.

### 17. User experience lengkap

- Task history dapat dibuka kembali.
- Progress tetap benar setelah refresh.
- Pending approval tetap muncul setelah login ulang.
- Offline device dijelaskan dengan jelas.
- User dapat memilih device target.
- User dapat membatalkan task.
- Error parsial ditampilkan secara natural.
- Review menunjukkan file yang akan berubah.
- Revoke device mempunyai re-authentication atau konfirmasi kuat.
- Startup Settings menunjukkan status service sebenarnya.
- Lengkapi loading, empty, error, success, offline, dan reconnect state.
- Verifikasi responsive dan accessibility dengan keyboard/screen reader.

## P1 — Security dan data integrity

### 18. Approval hardening

- Snapshot tool name dan argument harus immutable setelah approval dibuat.
- Validasi ulang permission saat approval dieksekusi.
- Validasi ulang ownership dan device target.
- Approval memiliki expiry.
- Approval tidak dapat digunakan ulang.
- Gunakan atomic state transition.
- Tambahkan idempotency saat double-click approve.
- File yang berubah setelah review harus membatalkan approval lama.
- Bulk delete wajib supervisor approval sesuai threshold.
- Audit approval mencatat before/after dan hasil verifikasi.

### 19. Filesystem safety

- Lindungi system paths lintas macOS, Windows, dan Linux.
- Tangani case-insensitive filesystem.
- Cegah path traversal.
- Cegah symlink escape.
- Cegah destination overwrite tanpa policy.
- Tentukan collision strategy.
- Gunakan temporary destination atau atomic rename jika relevan.
- Verifikasi copy dengan hash, bukan hanya ukuran.
- Tentukan delete ke Trash atau permanent delete.
- Sediakan undo bila product policy mengharuskannya.
- Jangan hapus folder non-empty tanpa scope yang jelas.
- Tambahkan disk-space preflight.
- Tangani file terkunci dan permission denied per item.

### 20. Credential storage

- Uji Keychain macOS.
- Uji Windows Credential Manager/DPAPI.
- Uji Linux Secret Service.
- Definisikan perilaku saat credential vault terkunci.
- Jangan fallback ke kunci yang mudah direkonstruksi pada production.
- Rotasi device key.
- Hapus secret vault saat logout/uninstall.
- Jangan pernah mencetak token/device key.
- Tambahkan file permission test pada macOS/Linux.
- Tambahkan threat model credential storage.

### 21. Audit integrity

- Pastikan user biasa tidak mempunyai endpoint mutasi audit.
- Audit setiap tindakan sensitif.
- Simpan source IP/request ID jika sesuai kebijakan privasi.
- Gunakan append-only permission di database.
- Tambahkan tamper detection atau export ke immutable log store.
- Redact password, token, document content, dan sensitive path bila perlu.
- Tambahkan retention dan export policy.
- Uji audit tidak hilang saat operasi gagal.

## P2 — Testing wajib PRD

### 22. Natural-language testing

- Greeting.
- Casual conversation tanpa tool.
- Ambiguous request.
- Contextual reference.
- Task request.
- Follow-up request.
- Provider nyata Mimo-compatible.
- Tool-call malformed.
- Provider timeout.
- Provider partial stream/disconnect.

### 23. File testing

- 10 file.
- 100 file.
- 1.000+ file.
- Duplicates dasar.
- Unsupported file dasar.
- Corrupted documents untuk setiap parser.
- Locked file simulasi.
- Locked file OS nyata.
- Permission denied nyata.
- Large file.
- Deep directory tree.
- Unicode filename.
- Symlink loop/escape.
- Low disk space.
- Destination collision.
- Partial batch failure.

### 24. Security testing

- User tidak dapat membaca task/conversation user lain.
- Memory antar-user terisolasi.
- User tidak dapat mengakses supervisor API.
- Device key salah ditolak.
- Destructive action melalui approval.
- IDOR seluruh endpoint.
- Approval replay/double-submit.
- Token expiry dan revoke.
- Brute-force/rate limit.
- Path traversal lintas OS.
- Symlink escape.
- Malicious filenames.
- Prompt injection dari isi dokumen.
- Secret leakage melalui log/error/stream.

### 25. Reliability testing

- AI provider unavailable dasar.
- Agent reconnect simulasi.
- Concurrent device dasar.
- Agent disconnect saat job berjalan.
- Server disconnect.
- Network interruption.
- Task timeout.
- Worker crash.
- Server restart.
- Job recovery.
- Duplicate delivery.
- Partial batch failure.
- Database unavailable.
- Queue unavailable.
- SSE reconnect.
- Reboot OS nyata.

### 26. Startup/platform matrix

Lakukan pada setiap OS yang benar-benar didukung:

- Instalasi bersih.
- Manual startup.
- Auto startup.
- Disable auto startup.
- Login/logout OS.
- Reboot.
- Network belum tersedia saat boot.
- Secure reconnect.
- Agent upgrade.
- Agent uninstall.
- Tidak membuka terminal mengganggu.

### 27. Frontend E2E

- Register/login/logout.
- Chat biasa.
- Recommendation rendering.
- Review approval.
- Approve dan cancel.
- Progress streaming.
- Refresh saat task berjalan.
- Device offline/reconnect.
- Device revoke.
- Supervisor employee management.
- Supervisor task monitoring.
- Supervisor approval.
- Responsive mobile/tablet/desktop.
- Keyboard navigation.
- Screen reader labels.
- Tidak ada console error.
- Natural error state tanpa stack trace.

### 28. Performance dan load test

- Scan 1.000, 10.000, dan jumlah target realistis.
- Ukur memory dan CPU Desktop Agent.
- Ukur waktu hash dan extraction.
- Banyak user mengirim chat bersamaan.
- Banyak device polling bersamaan.
- Banyak task dan approval bersamaan.
- Load test API.
- Soak test agent.
- Pastikan polling tidak membebani server berlebihan.
- Tetapkan SLO dan threshold penerimaan.

## P2 — Operasional produksi

### 29. Deployment production

- Pisahkan konfigurasi development, staging, dan production.
- Buat staging environment.
- Siapkan PostgreSQL.
- Siapkan durable queue dan worker.
- Siapkan reverse proxy/load balancer TLS.
- Gunakan secrets manager.
- Jalankan container sebagai non-root.
- Tambahkan resource limit.
- Tambahkan readiness dan liveness checks.
- Tambahkan rolling deployment.
- Tambahkan database migration step.
- Tambahkan rollback procedure.
- Hindari default supervisor password dalam Compose production.
- Uji disaster recovery.

### 30. Observability

- Metrics endpoint untuk monitoring system.
- AI response latency tersimpan.
- Task duration dan queue wait duration.
- Agent heartbeat age.
- Retry/reconnect counters.
- Job timeout/stale counters.
- Structured logging.
- Correlation/request/task ID.
- Error tracking.
- Dashboard operasional.
- Alerting untuk queue backlog, agent offline, error spike, dan provider down.
- Redaction data sensitif.

### 31. Backup dan recovery

- Backup database otomatis.
- Enkripsi backup.
- Retention policy.
- Restore drill.
- Recovery Point Objective.
- Recovery Time Objective.
- Recovery task/job setelah restart.
- Dokumentasi incident recovery.

### 32. Release management agent

- Semantic versioning.
- Update channel.
- Signed releases.
- Checksum package.
- Compatibility policy server-agent.
- Minimum supported version.
- Upgrade flow tanpa kehilangan config.
- Rollback agent.
- Uninstall bersih.
- Release notes.

### 33. Dokumentasi operasional

- README root dasar.
- Production deployment runbook.
- Environment variable reference lengkap.
- Agent installation per OS.
- Reboot/autostart verification guide.
- Backup/restore runbook.
- Incident response runbook.
- Key rotation procedure.
- Database migration procedure.
- Upgrade/rollback procedure.
- Troubleshooting device offline.
- Troubleshooting provider dan queue.
- Security model dan threat model.

## Urutan pengerjaan yang disarankan

1. Multi-device dan queue correctness.
2. Packaging Desktop Agent.
3. Startup Settings end-to-end.
4. PostgreSQL + durable worker queue.
5. Approval dan filesystem safety hardening.
6. Device monitoring dan configurable policy.
7. Incremental indexing/cache agent.
8. Task cancellation, timeout, retry, dan recovery.
9. Production security/TLS/rate limiting.
10. Lengkapi test PRD dan frontend E2E.
11. Load/performance testing.
12. Deployment staging.
13. Uji reboot pada OS target.
14. Security review.
15. Production readiness review dan baru kemudian release.

## Definisi “siap produksi”

RAPIIN baru layak dinyatakan siap produksi jika:

- seluruh acceptance criteria 1–20 mempunyai bukti test;
- tidak ada operasi file yang bisa melewati approval dan permission;
- task tidak hilang atau dieksekusi dua kali setelah restart;
- beberapa device satu user dapat aktif bersamaan;
- agent dapat di-install, auto-start, update, dan uninstall pada OS target;
- seluruh koneksi production menggunakan TLS;
- backup dan restore sudah diuji;
- monitoring dan alerting aktif;
- test keamanan, E2E, reliability, dan load lulus;
- alur nyata `chat → rekomendasi → approval → agent → verifikasi → laporan` lulus pada komputer user, bukan hanya sandbox server.
