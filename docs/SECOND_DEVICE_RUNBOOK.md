# Runbook laptop kedua

Runbook ini mempertahankan arsitektur PRD: satu Core Backend sebagai source of
truth dan satu RAPIIN Agent terminal pada setiap komputer pengguna. File tetap
diproses lokal pada perangkat yang dipilih; tidak ada remote shell.

## 1. Jaringan privat server

Backend tetap bind ke `127.0.0.1:8000`. Gunakan Tailscale Serve, bukan Funnel,
agar aplikasi hanya tersedia bagi perangkat yang masuk tailnet yang sama.

Di Mac server, setelah Tailscale aktif dan login:

```bash
tailscale serve --bg http://127.0.0.1:8000
tailscale serve status
tailscale status
```

Catat URL HTTPS yang ditampilkan. Tambahkan origin tersebut secara persis ke
`RAPIIN_ALLOWED_ORIGINS`, lalu restart `com.rapiin.server`. Jangan mengubah
`RAPIIN_HOST` menjadi `0.0.0.0`.

## 2. Persiapan laptop kedua

1. Pasang Tailscale dan login ke tailnet yang sama. Pastikan URL `/ready` dapat
   dibuka dan menghasilkan status `ready`.
2. Pasang `gh` dan `uv`, lalu login GitHub dengan akun yang mempunyai akses baca
   ke repository privat: `gh auth login`.
3. Jalankan installer rilis dari checkout repository:

```bash
./ops/install_rapiin_release.sh https://NAMA-MESIN.TAILNET.ts.net "$HOME/Downloads"
```

Installer mengunduh wheel rilis, memverifikasi SHA-256, meminta login RAPIIN
secara interaktif, membuat identity perangkat baru, mengaktifkan autostart, dan
menjalankan `rapiin verify`. Password tidak diberikan sebagai argumen agar
tidak masuk shell history.

## 3. Uji penerimaan dua perangkat

Gunakan folder disposable pada setiap laptop, bukan dokumen asli.

- Kedua perangkat tampil `ONLINE` pada Settings user.
- Chat menampilkan pemilih `Kerjakan di`; kirim scan ke laptop pertama dan
  kedua, lalu pastikan job hanya diambil target yang dipilih.
- Buat minimal satu file PDF dan satu duplikat di workspace laptop kedua.
  Verifikasi scan, rekomendasi terstruktur, Review, Approve, hasil mutasi, audit,
  dan hasil fisik file. Undo bukan persyaratan PRD V1.
- Matikan agent laptop kedua saat job read-only berjalan, hidupkan kembali,
  lalu verifikasi reconnect dan lease job pulih tanpa eksekusi ganda.
- Reboot laptop kedua. Setelah login jalankan `rapiin startup-probe verify` dan
  `rapiin verify`.
- Lepas laptop kedua melalui Settings. `rapiin verify` harus gagal. Jalankan
  setup kembali dan pastikan device key baru berhasil.
- Supervisor memeriksa employee, device, task, approval, dan audit tanpa dapat
  membaca isi file di luar metadata yang diizinkan.

Simpan tanggal, versi agent, nama kedua perangkat, task ID, approval ID, hasil
reboot, hasil revoke/re-pair, dan screenshot UI pada catatan acceptance. Jangan
menyimpan token, password, device key, atau isi dokumen pengguna.

## 4. Kriteria lulus

Deployment dua laptop belum boleh dinyatakan lulus sampai semua uji pada bagian
3 dijalankan terhadap laptop kedua fisik. CI dan simulasi database membuktikan
logika routing, tetapi bukan instalasi, keychain, autostart, reboot, jaringan,
atau permission filesystem pada mesin tersebut.
