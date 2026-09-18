"""Duplicate detection - hash based exact duplicate finder."""
from __future__ import annotations

from pathlib import Path

from ..permissions import check_path_allowed, resolve_path, sandbox_root
from .hashing import file_hash


def find_duplicates(conn, *, user_id: int, arguments: dict) -> dict:
    raw = arguments.get("path") or str(sandbox_root())
    root = resolve_path(sandbox_root(), raw)
    allowed, reason = check_path_allowed(sandbox_root(), str(root))
    if not allowed:
        raise PermissionError(f"Path ditolak kebijakan: {reason}")
    if not root.is_dir():
        raise FileNotFoundError(f"Folder tidak ditemukan: {root}")

    by_hash: dict[str, list[Path]] = {}
    for entry in root.rglob("*"):
        try:
            if not entry.is_file():
                continue
        except OSError:
            continue
        digest = file_hash(entry)
        by_hash.setdefault(digest, []).append(entry)
        if sum(len(v) for v in by_hash.values()) > 5000:
            break

    groups = []
    duplicate_count = 0
    for digest, paths in by_hash.items():
        if len(paths) > 1:
            paths_sorted = sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True)
            kept = paths_sorted[0]
            duplicates = paths_sorted[1:]
            duplicate_count += len(duplicates)
            groups.append({
                "hash": digest[:16],
                "keep": str(kept),
                "duplicates": [str(p) for p in duplicates],
                "count": len(duplicates),
            })

    groups.sort(key=lambda g: g["count"], reverse=True)
    return {"duplicate_groups": len(groups), "duplicate_files": duplicate_count, "groups": groups[:50]}
