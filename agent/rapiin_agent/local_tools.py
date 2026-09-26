"""Local filesystem tools executed by the Desktop Agent on the employee PC.

These mirror the server-side tool names so jobs from Hermes Core can run
locally. Only read/analysis tools are delegated to the agent (mutation jobs
stay server-side behind approvals).
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import time
import zipfile
from base64 import b64decode
from binascii import Error as BinasciiError
from pathlib import Path

MAX_FILES = 5000
MAX_TEXT_CHARS = 50_000
PROTECTED_PACKAGE_SUFFIXES = {
    ".photoslibrary",
    ".photolibrary",
    ".musiclibrary",
    ".imovielibrary",
    ".localized",
}
PROTECTED_PACKAGE_NAMES = {"photo booth library"}
# Skipped while scanning, so a folder walk stays quiet and readable.
PROTECTED_DIRECTORY_NAMES = {"library"}
# Top-level directories that keep macOS bootable. Checked at the root only, so a
# project's own bin/ or var/ folder is unaffected.
SYSTEM_CRITICAL_PATHS = {"system", "usr", "bin", "sbin", "dev"}
# macOS keeps /etc, system databases, and root's home under /private. Naming them
# explicitly matters: blocking all of /private would also lock out the per-user
# temp directories that /var/folders resolves to.
PRIVATE_SYSTEM_PATHS = (
    Path("/private/etc"),
    Path("/private/var/db"),
    Path("/private/var/audit"),
    Path("/private/var/root"),
)
# Key material that must never reach a model context, wherever it appears.
KEY_MATERIAL_NAMES = {
    ".ssh", ".aws", ".gnupg", ".kube", ".docker", ".rapiin",
    "keychains", "credentials", "secrets",
}
NON_USER_DUPLICATE_SUFFIXES = {
    ".db-shm",
    ".db-wal",
    ".sqlite-shm",
    ".sqlite-wal",
    ".lock",
}
FILE_LIST_CACHE_TTL_SECONDS = 30.0
_FILE_LIST_CACHE: dict[str, tuple[float, list[Path], dict[str, int]]] = {}
_HASH_CACHE: dict[tuple[str, int, int], str] = {}

try:
    from pypdf import PdfReader  # type: ignore
except Exception:  # pragma: no cover
    PdfReader = None

try:
    import docx  # type: ignore
except Exception:  # pragma: no cover
    docx = None

try:
    import openpyxl  # type: ignore
except Exception:  # pragma: no cover
    openpyxl = None

try:
    from pptx import Presentation  # type: ignore
except Exception:  # pragma: no cover
    Presentation = None


def _metadata(path: Path) -> dict:
    stat = path.stat()
    return {
        "name": path.name,
        "extension": path.suffix.lower(),
        "size": stat.st_size,
        "modified": stat.st_mtime,
    }


def _files_under(root: Path) -> list[Path]:
    """Return user-visible files without descending into app-managed bundles."""
    cache_key = str(root.expanduser().resolve())
    cached = _FILE_LIST_CACHE.get(cache_key)
    now = time.monotonic()
    if cached and now - cached[0] <= FILE_LIST_CACHE_TTL_SECONDS:
        directories_unchanged = True
        for directory, previous_mtime_ns in cached[2].items():
            try:
                if Path(directory).stat().st_mtime_ns != previous_mtime_ns:
                    directories_unchanged = False
                    break
            except OSError:
                directories_unchanged = False
                break
        if directories_unchanged:
            return list(cached[1])
    out: list[Path] = []
    directory_mtimes: dict[str, int] = {}
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        current_path = Path(current)
        try:
            directory_mtimes[str(current_path)] = current_path.stat().st_mtime_ns
        except OSError:
            continue
        directory_names[:] = [
            name
            for name in directory_names
            if not name.startswith(".")
            and name.lower() not in PROTECTED_PACKAGE_NAMES
            and name.casefold() not in PROTECTED_DIRECTORY_NAMES
            and Path(name).suffix.lower() not in PROTECTED_PACKAGE_SUFFIXES
            and not (current_path / name / ".git").exists()
        ]
        for name in file_names:
            if name.startswith("."):
                continue
            entry = Path(current) / name
            try:
                if not entry.is_file() or entry.is_symlink():
                    continue
            except OSError:
                continue
            out.append(entry)
            if len(out) >= MAX_FILES:
                _FILE_LIST_CACHE[cache_key] = (now, list(out), directory_mtimes)
                return out
    _FILE_LIST_CACHE[cache_key] = (now, list(out), directory_mtimes)
    return out


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(65536):
            digest.update(chunk)
    return digest.hexdigest()


def _cached_hash(path: Path) -> str:
    """Cache analysis hashes while keeping mutation verification uncached."""
    stat = path.stat()
    key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns)
    cached = _HASH_CACHE.get(key)
    if cached is not None:
        return cached
    digest = _hash(path)
    _HASH_CACHE[key] = digest
    if len(_HASH_CACHE) > MAX_FILES * 2:
        _HASH_CACHE.clear()
        _HASH_CACHE[key] = digest
    return digest


def _invalidate_analysis_caches() -> None:
    _FILE_LIST_CACHE.clear()
    _HASH_CACHE.clear()


def _fingerprint(path: Path) -> dict:
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": _hash(path),
    }


def _validate_fingerprint(path: Path, expected: dict | None) -> None:
    if not expected:
        return
    current = _fingerprint(path)
    if any(current.get(key) != expected.get(key) for key in ("path", "size", "mtime_ns", "sha256")):
        raise RuntimeError(f"File berubah sejak review dan tidak dijalankan: {path}")


def _parse_text(path: Path) -> str:
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            if PdfReader is None:
                return ""
            parts = []
            reader = PdfReader(str(path))
            for page in reader.pages[:50]:
                try:
                    parts.append(page.extract_text() or "")
                except Exception:
                    continue
            return "\n".join(parts)[:MAX_TEXT_CHARS]
        if suffix in {".doc", ".docx"}:
            if docx is None or suffix == ".doc":
                return ""
            document = docx.Document(str(path))
            return "\n".join(p.text for p in document.paragraphs)[:MAX_TEXT_CHARS]
        if suffix in {".xls", ".xlsx"}:
            if openpyxl is None or suffix == ".xls":
                return ""
            wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
            chunks = []
            for sheet_name in wb.sheetnames[:5]:
                sheet = wb[sheet_name]
                chunks.append(f"[Sheet: {sheet_name}]")
                for i, row in enumerate(sheet.iter_rows(values_only=True)):
                    if i >= 100:
                        break
                    values = ["" if v is None else str(v) for v in row]
                    if any(values):
                        chunks.append(" | ".join(values))
            wb.close()
            return "\n".join(chunks)[:MAX_TEXT_CHARS]
        if suffix in {".ppt", ".pptx"}:
            if Presentation is None or suffix == ".ppt":
                return ""
            prs = Presentation(str(path))
            chunks = []
            for idx, slide in enumerate(prs.slides[:50]):
                chunks.append(f"[Slide {idx + 1}]")
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text:
                        chunks.append(shape.text)
            return "\n".join(chunks)[:MAX_TEXT_CHARS]
        if suffix == ".csv":
            rows: list[str] = []
            with open(path, newline="", encoding="utf-8-sig", errors="replace") as fh:
                for row in csv.reader(fh):
                    rows.append(",".join(row))
                    if len(rows) >= 100:
                        break
            return "\n".join(rows)[:MAX_TEXT_CHARS]
        if suffix == ".json":
            return json.dumps(json.loads(path.read_text(encoding="utf-8")), indent=2, ensure_ascii=False)[:MAX_TEXT_CHARS]
        if suffix == ".zip":
            with zipfile.ZipFile(path) as zf:
                return json.dumps({"entries": zf.namelist()[:200]}, ensure_ascii=False)
        return path.read_text(encoding="utf-8", errors="replace")[:MAX_TEXT_CHARS]
    except Exception:
        return ""


def run_tool(kind: str, arguments: dict) -> dict:
    """Execute a tool locally. Read/analysis tools are always available;
    mutation tools require the target inside the agent workspace."""
    if kind == "filesystem_scanner":
        return _scan(arguments)
    if kind == "metadata_extractor":
        return _metadata_tool(arguments)
    if kind == "file_search":
        return _search(arguments)
    if kind == "duplicate_detector":
        return _duplicates(arguments)
    if kind == "document_parser":
        return _parse_document(arguments)
    if kind in {"pdf_parser", "spreadsheet_parser"}:
        return _parse_document(arguments)
    if kind == "file_classifier":
        return _classify(arguments)
    if kind == "folder_organizer":
        return _organize(arguments)
    if kind == "semantic_indexer":
        return _index(arguments)
    if kind == "semantic_search":
        return _semantic_search(arguments)
    if kind == "file_move":
        return _mutate(arguments, "move")
    if kind == "file_copy":
        return _mutate(arguments, "copy")
    if kind == "file_rename":
        return _mutate(arguments, "rename")
    if kind == "file_delete":
        return _mutate(arguments, "delete")
    if kind == "bulk_delete":
        return _mutate(arguments, "delete")
    if kind == "file_restore":
        from .trash import restore_trash

        return restore_trash(str(arguments.get("trash_id") or ""))
    if kind == "trash_list":
        from .trash import list_trash

        return list_trash()
    if kind == "file_mkdir":
        return _mkdir(arguments)
    if kind == "file_write":
        return _write_file(arguments)
    if kind == "file_edit":
        return _edit_file(arguments)
    if kind == "batch_executor":
        return _mutate(arguments, "batch")
    if kind == "verification":
        return _verify(arguments)
    return {"status": "ERROR", "message": f"Tool tidak dikenal: {kind}"}


def _verify(arguments: dict) -> dict:
    operation = arguments.get("operation")
    source = Path(arguments.get("source") or arguments.get("path") or "").expanduser()
    destination = Path(arguments.get("destination") or "").expanduser() if arguments.get("destination") else None
    _guard_mutation(source)
    if destination:
        _guard_mutation(destination)
    if operation == "delete":
        return {"status": "OK", "verified": not source.exists()}
    if operation == "move":
        verified = not source.exists() and bool(destination and destination.exists())
    elif operation in {"copy", "hash"}:
        verified = bool(source.exists() and destination and destination.exists() and _hash(source) == _hash(destination))
    else:
        return {"status": "ERROR", "message": "Operasi verifikasi tidak valid."}
    return {"status": "OK" if verified else "ERROR", "verified": verified}


def _guard_mutation(path: Path, destination: bool = False) -> None:
    """Refuse filesystem access outside allowed roots and protected paths.

    Access is intentionally wide: the assistant is expected to work across this
    laptop. Two groups stay closed because a mistake there is not recoverable by
    the assistant: paths that keep macOS bootable, and the stores that hold key
    material or app-private data.
    """
    from .config import allowed_roots

    candidate = path.expanduser().resolve()
    roots = [root.resolve() for root in allowed_roots()]
    if not any(_is_relative_to(candidate, root) for root in roots):
        shown = ", ".join(str(root) for root in roots)
        raise PermissionError(f"Path di luar workspace/folder yang diizinkan ({shown}): {path}")

    parts = [part.casefold() for part in candidate.parts]
    top_level = parts[1] if len(parts) > 1 else ""
    if top_level in SYSTEM_CRITICAL_PATHS:
        raise PermissionError(f"Folder sistem tidak dapat diakses RAPIIN: {path}")
    if any(_is_relative_to(candidate, private) for private in PRIVATE_SYSTEM_PATHS):
        raise PermissionError(f"Folder sistem tidak dapat diakses RAPIIN: {path}")
    if KEY_MATERIAL_NAMES.intersection(parts):
        raise PermissionError(f"Path sensitif tidak dapat diakses RAPIIN: {path}")

    # ~/Library and /Library carry keychains, cookies, and app-private data.
    home = Path.home().resolve()
    if _is_relative_to(candidate, home / "Library") or _is_relative_to(candidate, Path("/Library")):
        raise PermissionError(f"Folder sistem tidak dapat diakses RAPIIN: {path}")


def _is_relative_to(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _collect_mutation_paths(arguments: dict) -> list[str]:
    listed = arguments.get("paths") or arguments.get("files")
    source = arguments.get("source")
    # Compatible models sometimes express a folder in `source` and put the
    # selected filenames in `paths`. Resolve that unambiguous form instead of
    # silently treating the whole folder as the mutation target.
    if isinstance(listed, list) and listed:
        base = Path(str(source)).expanduser() if source else None
        return [
            str(base / str(item)) if base and not Path(str(item)).expanduser().is_absolute() else str(item)
            for item in listed
        ]
    raw = source or arguments.get("path") or listed
    if isinstance(raw, list):
        return [str(p) for p in raw]
    if raw:
        return [str(raw)]
    return []


MAX_WRITE_BYTES = 1024 * 1024  # 1 MB per created/edited file.

_AGENT_TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".jsonl",
    ".log", ".yml", ".yaml", ".xml", ".html", ".htm", ".css",
    ".js", ".ts", ".tsx", ".jsx", ".py", ".sh", ".sql", ".ini",
    ".cfg", ".toml", ".rtf",
}

_AGENT_READ_ONLY_BINARY = {".pdf", ".doc", ".docx", ".ppt", ".pptx"}


def _mkdir(arguments: dict) -> dict:
    raw = arguments.get("path")
    if not raw:
        return {"status": "ERROR", "message": "Parameter path wajib diisi."}
    target = Path(str(raw)).expanduser()
    try:
        _guard_mutation(target)
        if target.exists() and not target.is_dir():
            return {"status": "ERROR", "message": f"Sudah ada file dengan nama itu: {target}"}
        created = not target.exists()
        target.mkdir(parents=True, exist_ok=True)
        if not target.is_dir():
            return {"status": "ERROR", "message": f"Folder tidak terbentuk: {target}"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "ERROR", "message": str(exc)}
    return {"status": "OK", "path": str(target), "created": created, "executed_count": 1, "verified_count": 1}


def _write_file(arguments: dict) -> dict:
    raw = arguments.get("path")
    if not raw:
        return {"status": "ERROR", "message": "Parameter path wajib diisi."}
    if "content" not in arguments:
        return {"status": "ERROR", "message": "Parameter content wajib diisi."}
    target = Path(str(raw)).expanduser()
    try:
        _guard_mutation(target)
        if target.exists():
            return {"status": "ERROR", "message": f"Sudah ada; file tidak ditimpa: {target}"}
        content = arguments.get("content") or ""
        encoding = str(arguments.get("encoding") or "utf-8").lower()
        if encoding == "base64":
            try:
                data = b64decode(content, validate=True)
            except (BinasciiError, ValueError) as exc:
                return {"status": "ERROR", "message": f"Konten base64 tidak valid: {exc}"}
        elif encoding in {"utf-8", "utf8", "text"}:
            data = content.encode("utf-8")
        else:
            return {"status": "ERROR", "message": "Encoding harus 'utf-8' atau 'base64'."}
        if len(data) > MAX_WRITE_BYTES:
            return {"status": "ERROR", "message": "Konten melebihi batas 1024 KB."}
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        if not (target.exists() and target.stat().st_size == len(data)):
            return {"status": "ERROR", "message": f"File tidak terbentuk sempurna: {target}"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "ERROR", "message": str(exc)}
    return {"status": "OK", "path": str(target), "size": len(data), "executed_count": 1, "verified_count": 1}


def _edit_file(arguments: dict) -> dict:
    raw = arguments.get("path")
    if not raw:
        return {"status": "ERROR", "message": "Parameter path wajib diisi."}
    target = Path(str(raw)).expanduser()
    try:
        _guard_mutation(target)
        if not target.exists() or not target.is_file():
            return {"status": "ERROR", "message": f"File tidak ditemukan: {target}"}
        suffix = target.suffix.lower()
        if suffix in _AGENT_READ_ONLY_BINARY:
            return {"status": "ERROR", "message": f"Format {suffix} hanya bisa dibaca, belum bisa diubah dengan aman."}
        backup = target.with_name(target.name + ".bak")
        if not backup.exists():
            shutil.copy2(str(target), str(backup))
        if suffix == ".xlsx":
            outcome = _edit_xlsx(target, arguments)
        else:
            outcome = _edit_text_file(target, arguments)
        if not outcome["verified"]:
            return {"status": "ERROR", "message": "Hasil edit tidak terverifikasi; backup tersimpan di " + str(backup)}
    except Exception as exc:  # noqa: BLE001
        return {"status": "ERROR", "message": str(exc)}
    return {"status": "OK", "path": str(target), "backup": str(backup), "changed": outcome["changed"], "executed_count": 1, "verified_count": 1}


def _edit_text_file(target: Path, arguments: dict) -> dict:
    try:
        original = target.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        raise ValueError(f"File bukan teks UTF-8 yang bisa diubah: {exc}") from exc
    operation = arguments.get("operation") or "replace"
    if operation == "replace":
        old = arguments.get("old")
        new = arguments.get("new", "")
        if old is None or old == "":
            raise ValueError("Parameter old wajib diisi untuk replace.")
        try:
            limit = int(arguments.get("count", 1))
        except (TypeError, ValueError) as exc:
            raise ValueError("Parameter count harus angka.") from exc
        occurrences = original.count(old)
        if occurrences == 0:
            raise ValueError("Teks old tidak ditemukan di file.")
        updated = original.replace(old, new, limit if limit > 0 else occurrences)
        changed = min(occurrences, limit) if limit > 0 else occurrences
    elif operation == "append":
        addition = arguments.get("text", "")
        separator = "" if original.endswith("\n") or original == "" else "\n"
        updated = original + separator + addition
        changed = 1
    elif operation == "insert":
        try:
            line_no = int(arguments.get("line", 1))
        except (TypeError, ValueError) as exc:
            raise ValueError("Parameter line harus nomor baris.") from exc
        lines = original.splitlines(keepends=True)
        index = max(0, min(line_no - 1, len(lines)))
        addition = arguments.get("text", "")
        if addition and not addition.endswith("\n"):
            addition += "\n"
        lines.insert(index, addition)
        updated = "".join(lines)
        changed = 1
    else:
        raise ValueError("Operasi edit harus replace, insert, atau append.")
    if len(updated.encode("utf-8")) > MAX_WRITE_BYTES:
        raise ValueError("Hasil edit melebihi batas 1024 KB.")
    target.write_text(updated, encoding="utf-8")
    return {"changed": changed, "verified": target.read_text(encoding="utf-8") == updated}


def _edit_xlsx(target: Path, arguments: dict) -> dict:
    import openpyxl

    sheet_name = arguments.get("sheet")
    cell = arguments.get("cell")
    if not sheet_name or not cell:
        raise ValueError("Parameter sheet dan cell wajib diisi untuk XLSX.")
    if "value" not in arguments:
        raise ValueError("Parameter value wajib diisi untuk XLSX.")
    workbook = openpyxl.load_workbook(str(target))
    if sheet_name not in workbook.sheetnames:
        raise ValueError(f"Sheet tidak ditemukan: {sheet_name}")
    workbook[sheet_name][cell] = arguments.get("value")
    workbook.save(str(target))
    check = openpyxl.load_workbook(str(target), read_only=True, data_only=True)
    stored = check[sheet_name][cell].value
    check.close()
    return {"changed": 1, "verified": stored == arguments.get("value")}


def _mutate(arguments: dict, operation: str) -> dict:
    """Move/copy/rename/delete/batch inside the agent workspace."""

    _invalidate_analysis_caches()

    destination = arguments.get("destination")
    new_name = arguments.get("new_name")
    paths = _collect_mutation_paths(arguments)

    if operation == "rename":
        if not paths or not new_name:
            return {"status": "ERROR", "message": "Parameter path dan new_name wajib."}
        src = Path(paths[0]).expanduser()
        _guard_mutation(src)
        dst = src.with_name(new_name)
        _guard_mutation(dst)
        if not src.exists():
            return {"status": "ERROR", "message": f"File tidak ditemukan: {src}"}
        if dst.exists():
            return {"status": "ERROR", "message": f"Tujuan sudah ada; file tidak ditimpa: {dst}"}
        src.rename(dst)
        return {"status": "OK", "executed_count": 1, "verified_count": 1, "summary": [{"source": str(src), "destination": str(dst), "status": "VERIFIED"}]}

    if operation == "delete":
        if arguments.get("reversible"):
            # FULL_AUTO has no approval card, so a delete must be undoable.
            from .trash import trash_paths

            outcome = trash_paths(paths, note=str(arguments.get("note") or ""))
            return outcome
        results = []
        errors = []
        executed = verified = 0
        expected_by_path = {
            str(item.get("path")): item for item in (arguments.get("expected_files") or []) if item.get("path")
        }
        for raw in paths:
            p = Path(raw).expanduser()
            try:
                _guard_mutation(p)
                if not p.exists():
                    raise FileNotFoundError(f"File tidak ditemukan: {p}")
                _validate_fingerprint(p, expected_by_path.get(str(p.resolve())) or expected_by_path.get(str(p)))
                if p.is_dir() and not p.is_symlink():
                    shutil.rmtree(p)
                else:
                    p.unlink()
                executed += 1
                if not p.exists():
                    verified += 1
                    results.append({"path": str(p), "status": "VERIFIED"})
                else:
                    errors.append(f"{p}: masih ada")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{p}: {exc}")
                results.append({"path": str(p), "status": "FAILED", "error": str(exc)})
        overall = "ERROR" if executed == 0 and errors else ("PARTIAL" if errors else "OK")
        return {"status": overall, "planned_count": len(paths), "executed_count": executed, "verified_count": verified, "failed_count": len(errors), "errors": errors, "summary": results}

    # move / copy / batch
    if operation == "batch":
        op = arguments.get("operation")
        if op not in {"move", "copy", "delete"}:
            return {"status": "ERROR", "message": "Operasi batch harus move/copy/delete."}
        if op == "delete":
            return _mutate({**arguments, "paths": paths}, "delete")
        operation = op

    # Explicit per-item moves (structured recommendations).
    if arguments.get("moves"):
        return _run_explicit_moves(arguments["moves"], operation)

    if not destination or not paths:
        return {"status": "ERROR", "message": "Parameter source/paths dan destination wajib."}

    dest_dir = Path(destination).expanduser()
    _guard_mutation(dest_dir, destination=True)
    if dest_dir.exists() and not dest_dir.is_dir():
        return {"status": "ERROR", "message": f"Tujuan bukan folder: {dest_dir}"}
    dest_dir.mkdir(parents=True, exist_ok=True)

    results = []
    errors = []
    executed = verified = 0
    for raw in paths:
        src = Path(raw).expanduser()
        try:
            _guard_mutation(src)
            if not src.exists():
                raise FileNotFoundError(f"File tidak ditemukan: {src}")
            dst = dest_dir / src.name
            _guard_mutation(dst)
            if dst.exists():
                raise FileExistsError(f"Tujuan sudah ada; file tidak ditimpa: {dst}")
            if operation == "move":
                shutil.move(str(src), str(dst))
            else:
                shutil.copy2(str(src), str(dst))
            executed += 1
            ok = (operation == "move" and not src.exists() and dst.exists()) or (operation == "copy" and src.exists() and dst.exists() and _hash(src) == _hash(dst))
            if ok:
                verified += 1
                results.append({"source": str(src), "destination": str(dst), "status": "VERIFIED"})
            else:
                errors.append(f"{raw}: verifikasi gagal")
                results.append({"source": str(src), "status": "UNVERIFIED"})
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{raw}: {exc}")
            results.append({"source": str(raw), "status": "FAILED", "error": str(exc)})
    overall = "ERROR" if executed == 0 and errors else ("PARTIAL" if errors else "OK")
    return {"status": overall, "planned_count": len(paths), "executed_count": executed, "verified_count": verified, "failed_count": len(errors), "errors": errors, "summary": results}


def _run_explicit_moves(moves: list[dict], operation: str) -> dict:
    """Move/copy each item to its own destination (recommendation flow)."""
    results: list[dict] = []
    errors: list[str] = []
    executed = verified = 0
    for item in moves:
        src_raw = item.get("source")
        dest_raw = item.get("destination")
        entry: dict = {"source": src_raw, "status": "FAILED"}
        if not src_raw or not dest_raw:
            errors.append("item tanpa source/destination")
            entry["error"] = "source/destination kosong"
            results.append(entry)
            continue
        try:
            src = Path(src_raw).expanduser()
            _guard_mutation(src)
            if not src.exists():
                raise FileNotFoundError(f"File tidak ditemukan: {src}")
            _validate_fingerprint(src, item.get("expected"))
            dest = Path(dest_raw).expanduser()
            _guard_mutation(dest)
            if dest.is_dir():
                dest = dest / src.name
                _guard_mutation(dest)
            else:
                dest.mkdir(parents=True, exist_ok=True)
                dest = dest / src.name
                _guard_mutation(dest)
            if dest.exists():
                raise FileExistsError(f"Tujuan sudah ada; file tidak ditimpa: {dest}")
            if operation == "move":
                shutil.move(str(src), str(dest))
            else:
                shutil.copy2(str(src), str(dest))
            executed += 1
            ok = (operation == "move" and not src.exists() and dest.exists()) or (
                operation == "copy" and src.exists() and dest.exists() and _hash(src) == _hash(dest)
            )
            entry["destination"] = str(dest)
            if ok:
                entry["status"] = "VERIFIED"
                verified += 1
            else:
                entry["status"] = "UNVERIFIED"
                errors.append(f"{src_raw}: verifikasi gagal")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{src_raw}: {exc}")
            entry["error"] = str(exc)
        results.append(entry)
    overall = "ERROR" if executed == 0 and errors else ("PARTIAL" if errors else "OK")
    return {"status": overall, "planned_count": len(moves), "executed_count": executed, "verified_count": verified, "failed_count": len(errors), "errors": errors, "summary": results}


def _scan(arguments: dict) -> dict:
    raw = arguments.get("path") or "."
    root = Path(raw).expanduser()
    _guard_mutation(root)
    if not root.is_dir():
        return {"status": "ERROR", "message": f"Folder tidak ditemukan: {root}"}
    root = root.resolve()
    files = _files_under(root)
    # A scan is never a dead end: it always carries recommendations so the
    # user can act on the result instead of just reading a file list. Scanning
    # stays cheap on purpose (no content hashing), so duplicate detection is
    # left to `folder_organizer`, which is the deep-analysis entry point.
    top_level = [f for f in files if f.parent == root]
    recs = _build_recommendations(root, top_level, detect_duplicates=False)
    if not recs and files:
        # Files exist but only inside subfolders: nothing to regroup at this
        # level, so point the user at the folders that do have content.
        subfolders = sorted({p.parent.name for p in files})[:5]
        recs.append({
            "id": "in-subfolders", "kind": "already_tidy",
            "title": "Folder sudah tertata",
            "description": "File berada di dalam subfolder. Pindai subfolder tertentu untuk rekomendasi lebih rinci.",
            "file_count": len(files), "action": "none",
            "detail": {"jumlah_file": len(files), "subfolder": subfolders},
        })
    return {
        "status": "OK",
        "directory": str(root),
        "file_count": len(files),
        "files": [_metadata(f) for f in files[:200]],
        "truncated": len(files) > 200,
        "recommendations": recs,
    }


def _metadata_tool(arguments: dict) -> dict:
    path = Path(arguments.get("path", "")).expanduser()
    _guard_mutation(path)
    if not path.exists():
        return {"status": "ERROR", "message": f"File tidak ditemukan: {path}"}
    return {"status": "OK", **_metadata(path)}


def _search(arguments: dict) -> dict:
    root = Path(arguments.get("directory") or ".").expanduser()
    _guard_mutation(root)
    query = (arguments.get("query") or "").lower()
    ext = (arguments.get("extension") or "").lower().lstrip(".")
    if ext and not ext.startswith("."):
        ext = f".{ext}"
    matches = []
    if root.is_dir():
        for f in _files_under(root):
            if query and query not in f.name.lower():
                continue
            if ext and f.suffix.lower() != ext:
                continue
            matches.append(_metadata(f))
            if len(matches) >= 200:
                break
    return {"status": "OK", "query": query, "count": len(matches), "results": matches}


def _duplicates(arguments: dict) -> dict:
    root = Path(arguments.get("path") or ".").expanduser()
    _guard_mutation(root)
    if not root.is_dir():
        return {"status": "ERROR", "message": f"Folder tidak ditemukan: {root}"}
    by_hash: dict[str, list[Path]] = {}
    for f in _files_under(root):
        try:
            if f.stat().st_size == 0 or f.suffix.casefold() in NON_USER_DUPLICATE_SUFFIXES:
                continue
            by_hash.setdefault(_cached_hash(f), []).append(f)
        except OSError:
            continue
    groups = []
    count = 0
    for digest, paths in by_hash.items():
        if len(paths) > 1:
            ordered = sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True)
            count += len(ordered) - 1
            groups.append({"hash": digest[:16], "keep": str(ordered[0]), "duplicates": [str(p) for p in ordered[1:]]})
    return {"status": "OK", "duplicate_groups": len(groups), "duplicate_files": count, "groups": groups[:50]}


def _parse_document(arguments: dict) -> dict:
    path = Path(arguments.get("path", "")).expanduser()
    _guard_mutation(path)
    if not path.is_file():
        return {"status": "ERROR", "message": f"File tidak ditemukan: {path}"}
    text = _parse_text(path)
    return {"status": "OK", "path": str(path), "content_preview": text[:4000], "chars": len(text)}


def _classify(arguments: dict) -> dict:
    root = Path(arguments.get("path") or ".").expanduser()
    _guard_mutation(root)
    if not root.is_dir():
        return {"status": "ERROR", "message": f"Folder tidak ditemukan: {root}"}
    counts: dict[str, int] = {}
    for f in _files_under(root):
        cat = _category(f)
        counts[cat] = counts.get(cat, 0) + 1
    ordered = [{"category": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: x[1], reverse=True)]
    return {"status": "OK", "directory": str(root.resolve()), "file_count": sum(counts.values()), "categories": ordered}


def _category(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}:
        return "images"
    if ext in {".xls", ".xlsx", ".csv"}:
        return "spreadsheets"
    if ext in {".ppt", ".pptx"}:
        return "presentations"
    if ext in {".zip", ".rar", ".7z", ".tar", ".gz"}:
        return "archives"
    if ext in {".pdf", ".doc", ".docx", ".txt", ".md", ".rtf"}:
        return "documents"
    if ext in {".py", ".js", ".ts", ".html", ".css", ".json", ".sql"}:
        return "code"
    if ext in {".exe", ".msi", ".dmg", ".pkg", ".apk"}:
        return "installers"
    if ext in {".mp3", ".mp4", ".mov", ".wav"}:
        return "media"
    return "other"


YEAR_RE = re.compile(r"(19|20)\d{2}")
CATEGORY_NAMES = {
    "images": "Gambar", "spreadsheets": "Spreadsheet", "presentations": "Presentasi",
    "archives": "Arsip", "documents": "Dokumen", "code": "Kode",
    "installers": "Installer", "media": "Media", "other": "Lainnya",
}


def _build_recommendations(root: Path, files: list[Path], *, detect_duplicates: bool = True) -> list[dict]:
    """Build structured, actionable recommendations for a folder.

    Shared by `folder_organizer` and `filesystem_scanner` so a plain scan
    always ends with a concrete next step for the user (PRD 6.8 / 14). Never
    returns nothing for a non-empty folder: when no grouping or duplicate
    work stands out, an advisory entry still reports what was found.

    ``detect_duplicates`` is off for scans: hashing every file is the only
    expensive step here, and the scan is expected to stay cheap. The deep
    duplicate pass runs through `folder_organizer` instead.
    """
    recs: list[dict] = []
    by_category: dict[str, list[Path]] = {}
    by_year: dict[str, list[Path]] = {}
    by_hash: dict[str, list[Path]] = {}
    for path in files:
        try:
            by_category.setdefault(_category(path), []).append(path)
            match = YEAR_RE.search(path.name)
            if match:
                by_year.setdefault(match.group(0), []).append(path)
            if detect_duplicates:
                by_hash.setdefault(_cached_hash(path), []).append(path)
        except OSError:
            continue

    typed = {key: value for key, value in by_category.items() if key != "other" and len(value) >= 5}
    if typed:
        moves = [{"source": str(path), "destination": str(root / CATEGORY_NAMES[key]), "expected": _fingerprint(path)}
                 for key, paths in typed.items() for path in paths]
        recs.append({"id": "by-type", "kind": "create_folders_by_type", "title": "Buat folder berdasarkan jenis file",
                     "description": "Kelompokkan file ke folder sesuai jenisnya.", "file_count": len(moves), "action": "move",
                     "detail": {CATEGORY_NAMES[key]: len(paths) for key, paths in typed.items()},
                     "apply": {"tool_name": "batch_executor", "tool_args": {"operation": "move", "moves": moves}}})
    if by_year:
        moves = [{"source": str(path), "destination": str(root / year), "expected": _fingerprint(path)}
                 for year, paths in by_year.items() for path in paths]
        recs.append({"id": "by-year", "kind": "group_by_year", "title": "Kelompokkan file berdasarkan tahun",
                     "description": "Pindahkan file bernama tahun ke folder tahun masing-masing.", "file_count": len(moves), "action": "move",
                     "detail": {year: len(paths) for year, paths in by_year.items()},
                     "apply": {"tool_name": "batch_executor", "tool_args": {"operation": "move", "moves": moves}}})
    duplicates: list[Path] = []
    for paths in by_hash.values():
        if len(paths) > 1:
            ordered = sorted(paths, key=lambda p: p.stat().st_mtime_ns, reverse=True)
            duplicates.extend(ordered[1:])
    if duplicates:
        recs.append({"id": "duplicates", "kind": "delete_duplicates", "title": "Hapus file duplikat persis",
                     "description": "Hapus salinan identik dan pertahankan versi terbaru.", "file_count": len(duplicates), "action": "delete",
                     "detail": {"files_saved": len(duplicates)},
                     "apply": {"tool_name": "file_delete", "tool_args": {"paths": [str(p) for p in duplicates],
                               "expected_files": [_fingerprint(p) for p in duplicates]}}})

    if not recs and files:
        # Nothing worth reorganising: say so and summarise what is there, so a
        # scan never comes back without guidance.
        by_cat = {CATEGORY_NAMES.get(key, key): len(paths) for key, paths in by_category.items() if paths}
        recs.append({
            "id": "already-tidy", "kind": "already_tidy",
            "title": "Folder sudah rapi",
            "description": "Tidak ada pengelompokan mendesak. Isi folder sudah cukup tertata.",
            "file_count": len(files), "action": "none",
            "detail": by_cat,
        })
    return recs


def _organize(arguments: dict) -> dict:
    """Create an actionable, immutable-on-server recommendation snapshot locally."""
    root = Path(arguments.get("path") or ".").expanduser()
    _guard_mutation(root)
    if not root.is_dir():
        return {"status": "ERROR", "message": f"Folder tidak ditemukan: {root}"}
    root = root.resolve()
    files = [p for p in _files_under(root) if p.parent == root]
    recs = _build_recommendations(root, files)
    return {"status": "OK", "directory": str(root), "file_count": len(files), "recommendations": recs}


def _index_path() -> Path:
    from .config import CONFIG_DIR

    return CONFIG_DIR / "index.json"


def _load_index() -> list[dict]:
    try:
        raw = json.loads(_index_path().read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw.get("items") or []
        return raw if isinstance(raw, list) else []
    except Exception:
        return []


def _save_index(items: list[dict]) -> None:
    _index_path().parent.mkdir(parents=True, exist_ok=True)
    target = _index_path()
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps({"schema_version": 2, "items": items}, ensure_ascii=False), encoding="utf-8")
    temporary.replace(target)
    try:
        target.chmod(0o600)
    except OSError:
        pass


def _index(arguments: dict) -> dict:
    """Index files locally and persist to ~/.rapiin/index.json."""
    root = Path(arguments.get("path") or ".").expanduser()
    _guard_mutation(root)
    if not root.is_dir():
        return {"status": "ERROR", "message": f"Folder tidak ditemukan: {root}"}
    root = root.resolve()
    previous = {item.get("path"): item for item in _load_index() if item.get("path")}
    # Preserve entries belonging to other indexed roots. Entries under this
    # root are rebuilt from the live filesystem, which removes stale files.
    items = []
    for item in previous.values():
        try:
            Path(item["path"]).resolve().relative_to(root)
        except ValueError:
            items.append(item)
    indexed = unchanged = skipped = 0
    for f in _files_under(root):
        try:
            stat = f.stat()
            key = str(f.resolve())
            cached = previous.get(key)
            if cached and cached.get("size") == stat.st_size and abs(float(cached.get("modified", 0)) - stat.st_mtime) < 0.0001:
                items.append(cached)
                unchanged += 1
                continue
            items.append({
                "path": key,
                "name": f.name,
                "size": stat.st_size,
                "modified": stat.st_mtime,
                "hash": _hash(f),
                "text": _parse_text(f)[:2000],
            })
            indexed += 1
        except OSError:
            skipped += 1
            continue
        if indexed + unchanged >= 10000:
            break
    _save_index(items)
    live_paths = {str(f.resolve()) for f in _files_under(root)[:10000]}
    stale_removed = sum(1 for path in previous if _is_under(Path(path), root) and path not in live_paths)
    return {"status": "OK", "directory": str(root), "indexed": indexed, "unchanged": unchanged, "stale_removed": stale_removed, "skipped": skipped, "total": indexed + unchanged}


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root)
        return True
    except (ValueError, OSError):
        return False


def _semantic_search(arguments: dict) -> dict:
    """Search the persisted local index by name or content."""
    query = (arguments.get("query") or "").lower()
    if not query:
        return {"status": "ERROR", "message": "Parameter query wajib diisi."}
    results = []
    for item in _load_index():
        if query in item["name"].lower() or query in (item.get("text") or "").lower():
            results.append({
                "path": item["path"],
                "name": item["name"],
                "size": item["size"],
                "hash": item["hash"],
            })
        if len(results) >= 50:
            break
    return {"status": "OK", "query": query, "count": len(results), "results": results}
