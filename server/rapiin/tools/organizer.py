"""Structured file-organization recommendations (PRD 6.8, 14).

Hermes calls `folder_organizer` (read-only). It scans + classifies + detects
duplicates and returns structured, actionable recommendations the UI renders
as cards with Apply buttons. Applying a recommendation goes through the
normal approval flow and reuses filesystem tools.
"""
from __future__ import annotations

import re
from pathlib import Path

from ..permissions import check_path_allowed, resolve_path, sandbox_root
from .analysis import CATEGORY_RULES, classify_file
from .duplicate import find_duplicates
from .filesystem import _files_under

CATEGORY_NAMES = {
    "images": "Gambar",
    "spreadsheets": "Spreadsheet",
    "presentations": "Presentasi",
    "archives": "Arsip",
    "documents": "Dokumen",
    "code": "Kode",
    "installers": "Installer",
    "media": "Media",
    "other": "Lainnya",
}

YEAR_RE = re.compile(r"(19|20)\d{2}")


def _extract_year(name: str) -> str | None:
    match = YEAR_RE.search(name)
    return match.group(0) if match else None


def organize_recommendations(conn, *, user_id: int, arguments: dict) -> dict:
    """Produce structured recommendations for a messy folder."""
    raw = arguments.get("path") or str(sandbox_root())
    root = resolve_path(sandbox_root(), raw)
    allowed, reason = check_path_allowed(sandbox_root(), str(root))
    if not allowed:
        raise PermissionError(f"Path ditolak kebijakan: {reason}")
    if not root.is_dir():
        raise FileNotFoundError(f"Folder tidak ditemukan: {root}")

    files = _files_under(root, True)
    if not files:
        return {"status": "OK", "directory": str(root), "file_count": 0, "recommendations": []}

    # Category counts for "create folders by type".
    counts: dict[str, int] = {}
    by_cat: dict[str, list[str]] = {}
    year_counts: dict[str, int] = {}
    by_year: dict[str, list[str]] = {}
    for f in files:
        cat = classify_file(f)["category"]
        counts[cat] = counts.get(cat, 0) + 1
        by_cat.setdefault(cat, []).append(f.name)
        year = _extract_year(f.name)
        if year:
            year_counts[year] = year_counts.get(year, 0) + 1
            by_year.setdefault(year, []).append(f.name)

    recommendations: list[dict] = []
    rid = 1

    # 1. Create folders by document type.
    typed = {k: v for k, v in counts.items() if k != "other" and v >= 5}
    if typed:
        rec = {
            "id": rid,
            "kind": "create_folders_by_type",
            "title": "Buat folder berdasarkan jenis file",
            "description": "Kelompokkan file ke folder sesuai jenisnya (dokumen, gambar, spreadsheet, dll).",
            "file_count": sum(typed.values()),
            "action": "move",
            "detail": {CATEGORY_NAMES.get(k, k): v for k, v in sorted(typed.items(), key=lambda x: -x[1])},
        }
        recommendations.append(rec)
        rid += 1

    # 2. Group documents by year (files with year in the name).
    if year_counts:
        rec = {
            "id": rid,
            "kind": "group_by_year",
            "title": "Kelompokkan file berdasarkan tahun",
            "description": "Pindahkan file yang namanya memuat tahun ke folder tahun masing-masing.",
            "file_count": sum(year_counts.values()),
            "action": "move",
            "detail": {k: v for k, v in sorted(year_counts.items(), key=lambda x: -x[1])},
        }
        recommendations.append(rec)
        rid += 1

    # 3. Remove exact duplicates (hash-based).
    dups = find_duplicates(conn, user_id=user_id, arguments={"path": str(root)})
    dup_files = dups.get("duplicate_files", 0)
    dup_groups = dups.get("groups", [])
    if dup_files:
        rec = {
            "id": rid,
            "kind": "delete_duplicates",
            "title": "Hapus file duplikat persis",
            "description": "Hapus salinan duplikat dan pertahankan versi terbaru.",
            "file_count": dup_files,
            "action": "delete",
            "detail": {"group_count": dup_groups.__len__(), "files_saved": dup_files},
        }
        recommendations.append(rec)
        rid += 1

    return {
        "status": "OK",
        "directory": str(root),
        "file_count": len(files),
        "recommendations": recommendations,
    }


def build_apply_payload(recommendation: dict, directory: str, conn, user_id: int) -> tuple[str, dict]:
    """Translate a recommendation into (tool_name, tool_args) for execution."""
    kind = recommendation["kind"]
    root = resolve_path(sandbox_root(), directory)

    if kind == "delete_duplicates":
        dups = find_duplicates(conn, user_id=user_id, arguments={"path": str(root)})
        paths = [d for g in dups.get("groups", []) for d in g.get("duplicates", [])]
        tool = "file_delete" if len(paths) <= 20 else "bulk_delete"
        return tool, {"paths": paths}

    if kind in {"create_folders_by_type", "group_by_year"}:
        # Recompute mapping source file -> target folder.
        moves: list[dict] = []
        files = _files_under(root, False)  # top-level only to keep it safe
        for f in files:
            if kind == "create_folders_by_type":
                cat = classify_file(f)["category"]
                if cat == "other":
                    continue
                folder = CATEGORY_NAMES.get(cat, cat)
            else:  # group_by_year
                year = _extract_year(f.name)
                if not year:
                    continue
                folder = year
            target = root / folder
            if f.parent != target and f.name.lower() not in {".ds_store", ".localized"}:
                moves.append({"source": str(f), "destination": str(target)})

        # Deduplicate by source.
        seen = set()
        unique = []
        for m in moves:
            if m["source"] not in seen:
                seen.add(m["source"])
                unique.append(m)
        return "batch_executor", {"operation": "move", "moves": unique}

    raise ValueError("Rekomendasi tidak dikenal.")
