# RAPIIN Desktop Agent

Agent yang diinstall di komputer pegawai. Menjalankan operasi file **lokal** di komputer
user atas perintah server RAPIIN (PRD section 8-11).

## Instalasi

Untuk pengguna, install wheel rilis yang checksum-nya sudah diverifikasi langsung dari terminal:

```bash
uv tool install /path/rapiin_agent-VERSION-py3-none-any.whl
rapiin --help
```

Untuk laptop kedua yang mengakses Core Backend melalui Tailscale, gunakan
`ops/install_agent_release.sh URL_SERVER_HTTPS`. Installer mengambil rilis
privat melalui GitHub CLI, memverifikasi checksum, melakukan setup interaktif,
dan mengaktifkan autostart. Lihat `docs/SECOND_DEVICE_RUNBOOK.md`.

Untuk development lokal:

```bash
cd agent
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -e .
```

Setelah itu binary `rapiin-agent` tersedia di `.venv/bin/`.
Parser PDF, DOCX, XLSX, PPTX, gambar, CSV, JSON, ZIP, dan teks dipasang sebagai dependency standar agar capability yang didaftarkan selalu tersedia.

## First-run

```bash
# Daftar akun user dulu lewat API register, atau dari aplikasi klien yang memakai API ini.
rapiin setup --server http://127.0.0.1:8000
# akan menanyakan email & kata sandi, lalu mendaftarkan perangkat ini.
```

Opsi setup:
- `--server URL` : alamat server RAPIIN
- `--email`, `--password` : kredensial (bisa dilewatkan agar tidak interaktif)
- `--device-name NAMA` : nama perangkat (default `hostname-OS`)
- `--allow-folder PATH` : folder yang dapat diakses (dapat diulang)
- `--autostart` : aktifkan autostart setelah setup

Instalasi baru mengizinkan `Downloads`, `Documents`, dan `Desktop` secara
default. Folder kerja lain dapat dikelola tanpa instal ulang:

```bash
rapiin folders list
rapiin folders add "/path/ke/folder-kerja"
rapiin folders remove "/path/ke/folder-kerja"
```

## Menjalankan agent

```bash
rapiin
```

Agent akan:
1. Melakukan heartbeat ke server tiap beberapa detik (perangkat tampil ONLINE).
2. Mengambil job dari antrean server (scan, cari, metadata, duplikat, parse, klasifikasi).
3. Menjalankan operasi **lokal** di komputer ini.
4. Melaporkan hasil kembali ke server.

## Autostart

```bash
rapiin-agent autostart on    # daftarkan sebagai service saat login
rapiin-agent autostart off   # nonaktifkan dan hapus service RAPIIN
rapiin-agent autostart       # cek status
```

Platform:
- macOS: LaunchAgent (`~/Library/LaunchAgents/com.rapiin.agent.plist`)
- Linux: systemd user service (`~/.config/systemd/user/rapiin-agent.service`)
- Windows: Startup folder

## Status & logout

```bash
rapiin-agent status    # info server, email, device id, mode startup
rapiin-agent verify    # heartbeat, verifikasi identity, dan cek antrean
rapiin-agent logout    # hapus kredensial lokal
rapiin-agent upgrade --wheel /path/rapiin_agent-VERSION-py3-none-any.whl
rapiin-agent uninstall # matikan autostart dan hapus kredensial/state lokal
rapiin-agent startup-probe record # jalankan sebelum reboot
rapiin-agent startup-probe verify # jalankan setelah login kembali
```

## Lokasi kredensial

- macOS/Linux: `~/.rapiin/config.json`
- Windows: `%LOCALAPPDATA%\RAPIIN\config.json`

Server URL dan device id tersimpan di file konfigurasi. Device key dan token
disimpan di credential vault OS melalui `keyring`; bila vault tidak tersedia,
agent memakai fallback Fernet yang terikat identitas mesin. File konfigurasi
dibatasi ke permission user pada platform POSIX. Jangan dibagikan.

## Catatan keamanan

- Agent **tidak** menerima perintah shell bebas. Hanya menjalankan tool read/analisis
  yang terdaftar (scan, search, metadata, duplicate, parser, classifier, indexer).
- Semua tool file dibatasi ke daftar folder lokal yang dipilih. Home/root disk,
  `.ssh`, `.aws`, `.gnupg`, keychain, konfigurasi RAPIIN, dan file `.env`
  tetap ditolak. Operasi mutasi hanya diterima setelah approval server.
- Semua aktivitas dicatat di audit log server.
