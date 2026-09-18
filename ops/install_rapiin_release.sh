#!/bin/sh
set -eu

REPOSITORY="${RAPIIN_GITHUB_REPOSITORY:-naf2k/RAPIIN}"
RELEASE_TAG="${RAPIIN_AGENT_TAG:-rapiin-v1.0.0}"
SERVER_URL="${1:-}"
WORKSPACE="${2:-$HOME/Downloads}"

if [ -z "$SERVER_URL" ]; then
  echo "Pemakaian: $0 https://nama-mesin.tailnet.ts.net [folder-workspace]" >&2
  exit 2
fi
for command_name in gh uv shasum; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "[gagal] Perintah '$command_name' belum terpasang." >&2
    exit 1
  fi
done

download_dir="$(mktemp -d -t rapiin-agent-release)"
trap 'rm -rf "$download_dir"' EXIT HUP INT TERM

echo "[1/4] Mengunduh rilis privat $RELEASE_TAG..."
gh release download "$RELEASE_TAG" --repo "$REPOSITORY" --dir "$download_dir" \
  --pattern 'rapiin_agent-*.whl' --pattern 'rapiin_agent-*.tar.gz' --pattern SHA256SUMS

echo "[2/4] Memverifikasi checksum..."
(cd "$download_dir" && shasum -a 256 -c SHA256SUMS)

wheel_path="$(find "$download_dir" -maxdepth 1 -name 'rapiin_agent-*.whl' -print -quit)"
if [ -z "$wheel_path" ]; then
  echo "[gagal] Wheel agent tidak ditemukan pada rilis." >&2
  exit 1
fi

echo "[3/4] Memasang atau memperbarui RAPIIN Agent..."
if uv tool list 2>/dev/null | grep -q '^rapiin-agent '; then
  uv tool install --force "$wheel_path"
else
  uv tool install "$wheel_path"
fi

echo "[4/4] Pairing perangkat dan mengaktifkan autostart..."
rapiin setup --server "$SERVER_URL" --workspace "$WORKSPACE" --autostart
rapiin verify

echo "[ok] Instalasi selesai. Jalankan 'rapiin status' untuk melihat konfigurasi."
