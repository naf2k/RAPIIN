#!/usr/bin/env python3
"""Pastikan aset rilis mengikuti konvensi yang dipakai installer.

Kedua installer karyawan menurunkan nama aset dari tag rilis:

    tag  rapiin-v1.1.1
      -> rapiin_agent-1.1.1-py3-none-any.whl
      -> rapiin_agent-1.1.1.tar.gz
      -> SHA256SUMS

Bila sebuah rilis memakai tag lain (mis. `agent-v1.0.0`) atau nama aset lain,
pemasangan karyawan gagal di langkah pertama: installer sudah menghapus tag
default, jadi ia mengambil rilis TERBARU dan mengharapkan konvensi di atas.
Nama yang tidak cocok = unduhan 404.

Pemeriksa ini menangkap kelas bug itu sebelum rilis diumumkan.

Jalankan:
    python3 ops/check_release_assets.py                # rilis terbaru saja
    python3 ops/check_release_assets.py --tag rapiin-v1.1.1
    python3 ops/check_release_assets.py --all          # semua rilis bertag rapiin-v*
"""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request

DEFAULT_REPOSITORY = "naf2k/RAPIIN"
TAG_PATTERN = re.compile(r"^rapiin-v(?P<version>\d+\.\d+\.\d+)$")


def _token() -> str:
    """Token opsional; tanpa ini GitHub membatasi 60 permintaan/jam per IP."""
    for name in ("GITHUB_TOKEN", "GH_TOKEN"):
        value = os.environ.get(name)
        if value:
            return value
    return ""


def _get_json(url: str) -> object:
    headers = {
        "User-Agent": "RAPIIN-Release-Checker",
        "Accept": "application/vnd.github+json",
    }
    token = _token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            raise SystemExit(
                "GitHub API menolak permintaan (403). Kemungkinan batas laju terlampaui; "
                "set GITHUB_TOKEN atau jalankan 'gh auth token' lalu ekspor sebagai GH_TOKEN."
            ) from exc
        raise


def expected_assets(version: str) -> set[str]:
    return {
        f"rapiin_agent-{version}-py3-none-any.whl",
        f"rapiin_agent-{version}.tar.gz",
        "SHA256SUMS",
    }


def check_release(repository: str, release: dict) -> list[str]:
    """Kembalikan daftar masalah; kosong berarti rilis sehat."""
    tag = release.get("tag_name", "")
    problems: list[str] = []

    match = TAG_PATTERN.match(tag)
    if not match:
        return [f"tag '{tag}' tidak mengikuti pola rapiin-v<versi> (mis. rapiin-v1.1.1)"]

    version = match.group("version")
    assets = {asset["name"] for asset in release.get("assets", [])}
    wanted = expected_assets(version)

    missing = wanted - assets
    if missing:
        problems.append(f"aset hilang: {', '.join(sorted(missing))}")

    # SHA256SUMS harus memuat kedua berkas distribusi, kalau tidak installer
    # tidak bisa memverifikasi unduhan dan berhenti.
    sums_name = "SHA256SUMS"
    if sums_name in assets:
        sums_url = next(a["browser_download_url"] for a in release["assets"] if a["name"] == sums_name)
        text = ""
        if sums_url.startswith("http"):
            try:
                with urllib.request.urlopen(
                    urllib.request.Request(sums_url, headers={"User-Agent": "RAPIIN-Release-Checker"}),
                    timeout=30,
                ) as response:
                    text = response.read().decode("utf-8", "replace")
            except (urllib.error.URLError, OSError, ValueError) as exc:
                problems.append(f"tidak bisa membaca SHA256SUMS: {exc}")
        else:
            problems.append("URL unduhan SHA256SUMS tidak valid")
        if text:
            for name in (f"rapiin_agent-{version}-py3-none-any.whl", f"rapiin_agent-{version}.tar.gz"):
                if name in assets and name not in text:
                    problems.append(f"SHA256SUMS tidak memuat {name}")

    if release.get("draft"):
        problems.append("rilis masih berstatus draft (installer tidak akan menemukannya)")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Cek aset rilis sesuai konvensi installer.")
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--tag", default="", help="periksa satu tag tertentu")
    parser.add_argument("--all", action="store_true", help="periksa semua rilis rapiin-v*")
    args = parser.parse_args()

    if args.tag:
        releases = [_get_json(f"https://api.github.com/repos/{args.repository}/releases/tags/{args.tag}")]
    elif args.all:
        releases = _get_json(f"https://api.github.com/repos/{args.repository}/releases?per_page=100")
    else:
        releases = [_get_json(f"https://api.github.com/repos/{args.repository}/releases/latest")]

    if isinstance(releases, dict):
        releases = [releases]

    failed = 0
    checked = 0
    for release in releases:
        tag = release.get("tag_name", "?")
        if args.all and not TAG_PATTERN.match(tag):
            continue  # rilis lama/bertag lain bukan urusan konvensi ini
        checked += 1
        problems = check_release(args.repository, release)
        if problems:
            failed += 1
            print(f"[gagal] {tag}")
            for problem in problems:
                print(f"        - {problem}")
        else:
            print(f"[ok]    {tag}")

    if checked == 0:
        print("[gagal] tidak ada rilis yang diperiksa")
        return 1

    print(f"\n{checked - failed}/{checked} rilis sehat.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
