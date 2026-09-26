"""Document analysis tools: parsing, classification and semantic indexing.

Implements PRD tools document_parser, file_classifier and semantic_indexer.
All analysis stays local (no raw file content leaves the machine); only a
small extracted-text preview is stored in the agent_files index.
"""
from __future__ import annotations

from pathlib import Path

from ..database import utcnow_iso
from ..permissions import check_path_allowed, resolve_path, sandbox_root
from .parsing import parse_file

# Category detection based on extension + content signals. Ordered by
# specificity so documents like "Laporan_2024.pdf" land in documents not misc.
CATEGORY_RULES: list[tuple[str, set[str], list[str]]] = [
    ("images", {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".svg"}, []),
    ("spreadsheets", {".xls", ".xlsx", ".csv"}, ["sheet", "tab", "data", "jumlah", "total", "harga", "rekap"]),
    ("presentations", {".ppt", ".pptx"}, ["slide", "presentasi", "deck"]),
    ("archives", {".zip", ".rar", ".7z", ".tar", ".gz"}, []),
    ("documents", {".pdf", ".doc", ".docx", ".txt", ".md", ".rtf"}, ["laporan", "surat", "dokumen", "invoice", "kontrak", "memo", "notulen"]),
    ("code", {".py", ".js", ".ts", ".html", ".css", ".json", ".sql", ".java", ".go", ".rs"}, []),
    ("installers", {".exe", ".msi", ".dmg", ".pkg", ".apk", ".deb"}, []),
    ("media", {".mp3", ".mp4", ".mov", ".wav", ".avi", ".mkv"}, []),
    ("other", set(), []),
]


def parse_and_summarize(conn, *, user_id: int, arguments: dict) -> dict:
    """Parse a single document and return extracted text summary + meta."""
    raw = arguments.get("path")
    if not raw:
        raise ValueError("Parameter path wajib diisi.")
    path = resolve_path(sandbox_root(), raw)
    allowed, reason = check_path_allowed(sandbox_root(), str(path))
    if not allowed:
        raise PermissionError(f"Path ditolak kebijakan: {reason}")
    if not path.is_file():
        raise FileNotFoundError(f"File tidak ditemukan: {path}")

    parsed = parse_file(path)
    text = parsed.get("extracted_text") or ""
    summary = text[:4000] + ("\n…[dipotong]" if len(text) > 4000 else "")
    classification = classify_file(path)
    result = {
        "path": str(path),
        "structure": parsed.get("structure"),
        "meta": parsed.get("meta", {}),
        "content_preview": summary,
        "category": classification["category"],
    }
    if parsed.get("error"):
        result["error"] = parsed["error"]
    return result


def classify_file(path: Path) -> dict:
    """Classify a single file into a category with confidence signals."""
    name = path.name.lower()
    ext = path.suffix.lower()
    text_hint = ""
    if ext in {".pdf", ".docx", ".txt", ".md", ".csv", ".xlsx"} and path.stat().st_size < 512 * 1024:
        try:
            parsed = parse_file(path)
            text_hint = (parsed.get("extracted_text") or "")[:2000].lower()
        except Exception:  # noqa: BLE001
            text_hint = ""

    best_category = "other"
    best_score = 0
    for category, exts, keywords in CATEGORY_RULES:
        score = 0
        if ext in exts:
            score += 2
        for kw in keywords:
            if kw in name or kw in text_hint:
                score += 1
        if score > best_score:
            best_score = score
            best_category = category

    return {"category": best_category, "file": path.name, "extension": ext}


def classify_folder(conn, *, user_id: int, arguments: dict) -> dict:
    """Classify files under a directory and group counts by category."""
    raw = arguments.get("path") or str(sandbox_root())
    root = resolve_path(sandbox_root(), raw)
    allowed, reason = check_path_allowed(sandbox_root(), str(root))
    if not allowed:
        raise PermissionError(f"Path ditolak kebijakan: {reason}")
    if not root.is_dir():
        raise FileNotFoundError(f"Folder tidak ditemukan: {root}")

    counts: dict[str, int] = {}
    samples: dict[str, list[str]] = {}
    total = 0
    for entry in root.rglob("*"):
        try:
            if not entry.is_file():
                continue
        except OSError:
            continue
        result = classify_file(entry)
        counts[result["category"]] = counts.get(result["category"], 0) + 1
        samples.setdefault(result["category"], []).append(entry.name)
        total += 1
        if total >= 5000:
            break

    # Sort by count desc for readability.
    ordered = [
        {"category": k, "count": counts[k], "files": samples[k][:10]}
        for k in sorted(counts, key=lambda c: counts[c], reverse=True)
    ]
    return {"directory": str(root), "file_count": total, "categories": ordered}


def index_files(conn, *, user_id: int, arguments: dict) -> dict:
    """Incremental index under a directory (PRD section 15).

    Uses the agent_files table as a hash/mtime cache: unchanged files are
    skipped, only new/changed files are hashed and parsed. Raw content is
    never uploaded; only a truncated preview is stored.
    """
    raw = arguments.get("path") or str(sandbox_root())
    root = resolve_path(sandbox_root(), raw)
    allowed, reason = check_path_allowed(sandbox_root(), str(root))
    if not allowed:
        raise PermissionError(f"Path ditolak kebijakan: {reason}")
    if not root.is_dir():
        raise FileNotFoundError(f"Folder tidak ditemukan: {root}")

    from .hashing import file_hash

    device_id = arguments.get("device_id")
    indexed = 0
    unchanged = 0
    skipped = 0
    errors: list[str] = []
    for entry in root.rglob("*"):
        try:
            if not entry.is_file():
                continue
            stat = entry.stat()
        except OSError:
            continue
        try:
            # Cache check: skip when size + mtime unchanged since last index.
            cached = conn.execute(
                "SELECT size, mtime FROM agent_files WHERE user_id = ? AND path = ?",
                (user_id, str(entry)),
            ).fetchone()
            if (
                cached is not None
                and cached["size"] == stat.st_size
                and cached["mtime"] is not None
                and abs(float(cached["mtime"]) - stat.st_mtime) < 0.0001
            ):
                unchanged += 1
                continue

            digest = file_hash(entry) if stat.st_size < 64 * 1024 * 1024 else ""
            parsed = parse_file(entry) if stat.st_size < 4 * 1024 * 1024 else {}
            text_preview = (parsed.get("extracted_text") or "")[:4000]
            conn.execute(
                """
                INSERT INTO agent_files (user_id, device_id, path, file_hash, size, mtime, extracted_text, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (user_id, device_id, path) DO UPDATE SET
                    file_hash = excluded.file_hash, size = excluded.size,
                    mtime = excluded.mtime, extracted_text = excluded.extracted_text,
                    indexed_at = excluded.indexed_at
                """,
                (user_id, device_id, str(entry), digest, stat.st_size, stat.st_mtime, text_preview, utcnow_iso()),
            )
            indexed += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{entry.name}: {exc}")
            skipped += 1
        if indexed + unchanged + skipped >= 3000:
            break
    return {
        "directory": str(root),
        "indexed": indexed,
        "unchanged_skipped": unchanged,
        "skipped": skipped,
        "errors": errors[:5],
    }


def search_index(conn, *, user_id: int, arguments: dict) -> dict:
    """Search the local index by filename or extracted text (semantic search)."""
    query = (arguments.get("query") or "").lower()
    if not query:
        raise ValueError("Parameter query wajib diisi.")
    rows = conn.execute(
        """
        SELECT path, file_hash, size, indexed_at, substr(extracted_text, 1, 500) AS preview
        FROM agent_files
        WHERE user_id = ?
          AND (lower(path) LIKE ? OR lower(extracted_text) LIKE ?)
        ORDER BY indexed_at DESC LIMIT 50
        """,
        (user_id, f"%{query}%", f"%{query}%"),
    ).fetchall()
    return {"query": query, "count": len(rows), "results": [dict(r) for r in rows]}
