#!/bin/sh
# RAPIIN Desktop Agent installer untuk macOS/Linux.
#
# Pemakaian:
#   sh install_rapiin_release.sh https://NAMA-SERVER.ts.net [folder-workspace]
#
# Alur: unduh rilis resmi terbaru dari GitHub -> verifikasi checksum SHA-256 ->
# pasang agent lewat uv -> pairing perangkat + autostart.
#
# Tidak butuh GitHub CLI: repositori bersifat publik, jadi unduhan memakai HTTPS
# biasa. Set RAPIIN_AGENT_TAG untuk memakai rilis tertentu (mis. rapiin-v1.1.0)
# dan RAPIIN_GITHUB_REPOSITORY untuk repositori lain.
set -eu

REPOSITORY="${RAPIIN_GITHUB_REPOSITORY:-naf2k/RAPIIN}"
RELEASE_TAG="${RAPIIN_AGENT_TAG:-}"
SERVER_URL="${1:-}"
WORKSPACE="${2:-$HOME/Downloads}"

if [ -z "$SERVER_URL" ]; then
  echo "Pemakaian: $0 https://nama-mesin.tailnet.ts.net [folder-workspace]" >&2
  exit 2
fi

# Pastikan perintah buatan uv (dir tool) dikenal shell ini.
PATH="$HOME/.local/bin:$PATH"
export PATH

if ! command -v curl >/dev/null 2>&1; then
  echo "[gagal] Perintah 'curl' belum terpasang." >&2
  exit 1
fi
if ! command -v shasum >/dev/null 2>&1; then
  echo "[gagal] Perintah 'shasum' belum tersedia untuk verifikasi checksum." >&2
  exit 1
fi

# uv yang memasang agent; kalau belum ada, pasang otomatis.
if ! command -v uv >/dev/null 2>&1; then
  echo "[info] uv belum ada, memasang otomatis..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
if ! command -v uv >/dev/null 2>&1; then
  echo "[gagal] uv belum tersedia. Buka terminal baru, lalu ulangi script ini." >&2
  exit 1
fi

# Tentukan rilis: pakai RAPIIN_AGENT_TAG bila diisi, selain itu ambil terbaru.
if [ -z "$RELEASE_TAG" ]; then
  echo "[info] Mencari rilis terbaru di $REPOSITORY..."
  RELEASE_TAG="$(curl -fsSL "https://api.github.com/repos/$REPOSITORY/releases/latest" \
    | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
fi
if [ -z "$RELEASE_TAG" ]; then
  echo "[gagal] Tidak menemukan rilis di $REPOSITORY." >&2
  exit 1
fi

# Nama aset mengikuti versi pada tag: rapiin-v1.1.0 -> rapiin_agent-1.1.0-*.whl
RELEASE_VERSION="${RELEASE_TAG#rapiin-v}"
BASE_URL="https://github.com/$REPOSITORY/releases/download/$RELEASE_TAG"
WHEEL_NAME="rapiin_agent-$RELEASE_VERSION-py3-none-any.whl"

download_dir="$(mktemp -d -t rapiin-agent-release)"
trap 'rm -rf "$download_dir"' EXIT HUP INT TERM

echo "[1/4] Mengunduh rilis $RELEASE_TAG..."
curl -fsSL -o "$download_dir/$WHEEL_NAME" "$BASE_URL/$WHEEL_NAME"
curl -fsSL -o "$download_dir/SHA256SUMS" "$BASE_URL/SHA256SUMS"

echo "[2/4] Memverifikasi checksum..."
if ! grep -q "$WHEEL_NAME" "$download_dir/SHA256SUMS"; then
  echo "[gagal] Checksum untuk $WHEEL_NAME tidak ada di SHA256SUMS." >&2
  exit 1
fi
grep "$WHEEL_NAME" "$download_dir/SHA256SUMS" > "$download_dir/CHECKSUM"
(cd "$download_dir" && shasum -a 256 -c CHECKSUM)

echo "[3/4] Memasang atau memperbarui RAPIIN Agent..."
if uv tool list 2>/dev/null | grep -q '^rapiin-agent '; then
  uv tool install --force "$download_dir/$WHEEL_NAME"
else
  uv tool install "$download_dir/$WHEEL_NAME"
fi

echo "[4/4] Pairing perangkat dan mengaktifkan autostart..."
rapiin setup --server "$SERVER_URL" --workspace "$WORKSPACE" --autostart
rapiin verify

echo "[ok] Instalasi selesai. Jalankan 'rapiin status' untuk melihat konfigurasi."
