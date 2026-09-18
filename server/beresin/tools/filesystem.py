"""Filesystem tools - scanning, metadata, search and mutation within a sandbox."""
from __future__ import annotations

import base64
import binascii
import shutil
import zipfile
from io import BytesIO
from pathlib import Path

from ..permissions import check_path_allowed, resolve_path, sandbox_root
from . import verify as verify_tool

SUPPORTED_EXTENSIONS = {
    ".txt", ".csv", ".md", ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".ppt", ".pptx", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".zip",
}

MAX_SCAN_FILES = 5000


def _protected_guard(path: Path) -> None:
    allowed, reason = check_path_allowed(sandbox_root(), str(path))
    if not allowed:
        raise PermissionError(f"Path ditolak kebijakan: {reason}")


def _resolve(raw: str) -> Path:
    return resolve_path(sandbox_root(), raw)


def _metadata(path: Path) -> dict:
    stat = path.stat()
    return {
        "name": path.name,
        "extension": path.suffix.lower(),
        "size": stat.st_size,
        "modified": stat.st_mtime,
    }


def _files_under(root: Path, recursive: bool, extensions: set[str] | None = None) -> list[Path]:
    out: list[Path] = []
    iterator = root.rglob("*") if recursive else root.iterdir()
    for entry in iterator:
        try:
            if not entry.is_file():
                continue
        except OSError:
            continue
        if extensions is not None and entry.suffix.lower() not in extensions:
            continue
        out.append(entry)
        if len(out) >= MAX_SCAN_FILES:
            break
    return out


def scan_directory(conn, *, user_id: int, arguments: dict) -> dict:
    raw = arguments.get("path") or str(sandbox_root())
    root = _resolve(raw)
    _protected_guard(root)
    if not root.is_dir():
        raise FileNotFoundError(f"Folder tidak ditemukan: {root}")

    recursive = bool(arguments.get("recursive", True))
    files = _files_under(root, recursive)
    items = [_metadata(p) for p in files]

    folders = []
    try:
        for entry in root.iterdir():
            if entry.is_dir():
                folders.append(entry.name)
    except OSError:
        pass

    return {
        "directory": str(root),
        "file_count": len(items),
        "files": items[:200],
        "folders": folders[:100],
        "truncated": len(items) > 200,
    }


def extract_metadata(conn, *, user_id: int, arguments: dict) -> dict:
    raw = arguments.get("path")
    if not raw:
        raise ValueError("Parameter path wajib diisi.")
    path = _resolve(raw)
    _protected_guard(path)
    if not path.exists():
        raise FileNotFoundError(f"File tidak ditemukan: {path}")
    return _metadata(path)


def search_files(conn, *, user_id: int, arguments: dict) -> dict:
    directory = arguments.get("directory") or str(sandbox_root())
    root = _resolve(directory)
    _protected_guard(root)
    query = (arguments.get("query") or "").lower()
    extension = (arguments.get("extension") or "").lower().lstrip(".")
    if extension and not extension.startswith("."):
        extension = f".{extension}"

    matches: list[dict] = []
    for path in _files_under(root, True):
        if query and query not in path.name.lower():
            continue
        if extension and path.suffix.lower() != extension:
            continue
        matches.append(_metadata(path))
        if len(matches) >= 200:
            break
    return {"query": query, "count": len(matches), "results": matches}


def move_files(conn, *, user_id: int, arguments: dict) -> dict:
    return _batch_operation(arguments, "move")


def copy_files(conn, *, user_id: int, arguments: dict) -> dict:
    return _batch_operation(arguments, "copy")


def rename_files(conn, *, user_id: int, arguments: dict) -> dict:
    raw_path = arguments.get("path")
    new_name = arguments.get("new_name")
    if not raw_path or not new_name:
        raise ValueError("Parameter path dan new_name wajib diisi.")
    source = _resolve(raw_path)
    _protected_guard(source)
    if not source.exists():
        raise FileNotFoundError(f"File tidak ditemukan: {source}")
    target = source.with_name(new_name)
    _protected_guard(target)
    if target.exists():
        raise FileExistsError(f"Tujuan sudah ada; file tidak ditimpa: {target}")
    source.rename(target)

    # Verify: the old name must be gone and the new name must exist.
    check = verify_tool.verify_move(str(source), str(target))
    if not check.get("verified"):
        return {
            "executed_count": 1,
            "verified_count": 0,
            "failed_count": 1,
            "errors": [check.get("reason", "Verifikasi gagal.")],
            "summary": [{"source": str(source), "destination": str(target), "status": "UNVERIFIED"}],
        }
    return {
        "executed_count": 1,
        "verified_count": 1,
        "failed_count": 0,
        "errors": [],
        "summary": [{"source": str(source), "destination": str(target), "status": "VERIFIED"}],
    }


def delete_files(conn, *, user_id: int, arguments: dict) -> dict:
    raw = arguments.get("path") or arguments.get("paths")
    paths = _collect_paths(raw)
    if not paths:
        raise ValueError("Parameter path wajib diisi.")

    results: list[dict] = []
    errors: list[str] = []
    executed = 0
    verified = 0
    for raw_path in paths:
        path = _resolve(raw_path)
        entry: dict = {"path": str(path), "status": "FAILED"}
        try:
            _protected_guard(path)
            if not path.exists():
                raise FileNotFoundError(f"File tidak ditemukan: {path}")
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
            executed += 1

            # Verify the path is really gone (PRD section 29).
            check = verify_tool.verify_delete(str(path))
            if check.get("verified"):
                entry["status"] = "VERIFIED"
                verified += 1
            else:
                entry["status"] = "UNVERIFIED"
                entry["warning"] = check.get("reason")
                errors.append(f"{path}: {check.get('reason')}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{path}: {exc}")
            entry["error"] = str(exc)
        results.append(entry)
    return {
        "planned_count": len(paths),
        "executed_count": executed,
        "verified_count": verified,
        "failed_count": len(errors),
        "errors": errors,
        "summary": results,
    }


def execute_batch(conn, *, user_id: int, arguments: dict) -> dict:
    """Apply an operation ('move', 'copy', 'delete') to many files.

    Supports either a single destination with `paths`, or explicit per-item
    `moves: [{source, destination}]` (used by structured recommendations).
    """
    operation = arguments.get("operation")
    destination = arguments.get("destination")
    raw_paths = arguments.get("paths") or arguments.get("files") or []
    moves = arguments.get("moves")

    if operation not in {"move", "copy", "delete"}:
        raise ValueError("Operasi batch harus move, copy, atau delete.")

    if moves:
        if operation == "delete":
            return delete_files(conn, user_id=user_id, arguments={"paths": [m["source"] for m in moves]})
        return _run_explicit_moves(moves, operation)

    if not raw_paths:
        raise ValueError("Daftar file kosong.")
    if operation == "delete":
        return delete_files(conn, user_id=user_id, arguments={"paths": raw_paths})
    return _run_move_copy(raw_paths, destination, operation)


def _run_explicit_moves(moves: list[dict], operation: str) -> dict:
    """Move/copy each item to its own destination, verifying each result."""
    results: list[dict] = []
    errors: list[str] = []
    executed = 0
    verified = 0
    for item in moves:
        source_raw = item.get("source")
        dest_raw = item.get("destination")
        entry: dict = {"source": source_raw, "status": "FAILED"}
        if not source_raw or not dest_raw:
            errors.append("item tanpa source/destination")
            entry["error"] = "source/destination kosong"
            results.append(entry)
            continue
        try:
            source = _resolve(source_raw)
            _protected_guard(source)
            if not source.exists():
                raise FileNotFoundError(f"File tidak ditemukan: {source}")
            # Destination may be a folder (keep name) or a full target path.
            dest = _resolve(dest_raw)
            _protected_guard(dest)
            if dest.is_dir():
                dest = dest / source.name
                _protected_guard(dest)
            else:
                # Treat as a folder path and create it (recommendation flows
                # create new category/year folders).
                dest.mkdir(parents=True, exist_ok=True)
                dest = dest / source.name
                _protected_guard(dest)
            if dest.exists():
                raise FileExistsError(f"Tujuan sudah ada; file tidak ditimpa: {dest}")
            if operation == "move":
                shutil.move(str(source), str(dest))
                check = verify_tool.verify_move(str(source), str(dest))
            else:
                shutil.copy2(str(source), str(dest))
                check = verify_tool.verify_copy(str(source), str(dest))
            executed += 1
            entry["destination"] = str(dest)
            if check.get("verified"):
                entry["status"] = "VERIFIED"
                verified += 1
            else:
                entry["status"] = "UNVERIFIED"
                entry["warning"] = check.get("reason")
                errors.append(f"{source_raw}: {check.get('reason')}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{source_raw}: {exc}")
            entry["error"] = str(exc)
        results.append(entry)
    return {
        "planned_count": len(moves),
        "executed_count": executed,
        "verified_count": verified,
        "failed_count": len(errors),
        "errors": errors,
        "summary": results,
    }


def _collect_paths(raw) -> list[str]:
    if isinstance(raw, list):
        return [str(p) for p in raw]
    if raw:
        return [str(raw)]
    return []


def _batch_operation(arguments: dict, operation: str) -> dict:
    destination = arguments.get("destination")
    raw = arguments.get("source") or arguments.get("paths")
    paths = _collect_paths(raw)
    if not destination or not paths:
        raise ValueError("Parameter source/paths dan destination wajib diisi.")
    return _run_move_copy(paths, destination, operation)


def _run_move_copy(raw_paths: list[str], destination: str | None, operation: str) -> dict:
    """Run move/copy for many files, then verify each result on disk.

    Verification follows PRD section 29: after executing, we check the
    source (gone for move) and destination (exists; size matches for copy)
    before counting the item as verified.
    """
    if not destination:
        raise ValueError("Parameter destination wajib diisi.")
    dest = _resolve(destination)
    _protected_guard(dest)
    if not dest.is_dir():
        raise FileNotFoundError(f"Folder tujuan tidak ditemukan: {dest}")

    results: list[dict] = []
    errors: list[str] = []
    executed = 0
    verified = 0
    for raw_path in raw_paths:
        source = _resolve(raw_path)
        entry: dict = {"source": str(source), "status": "FAILED"}
        try:
            _protected_guard(source)
            if not source.exists():
                raise FileNotFoundError(f"File tidak ditemukan: {source}")
            target = dest / source.name
            _protected_guard(target)
            if target.exists():
                raise FileExistsError(f"Tujuan sudah ada; file tidak ditimpa: {target}")
            if operation == "move":
                shutil.move(str(source), str(target))
            else:
                shutil.copy2(str(source), str(target))
            executed += 1

            # Verify what actually happened on disk.
            if operation == "move":
                check = verify_tool.verify_move(str(source), str(target))
            else:
                check = verify_tool.verify_copy(str(source), str(target))

            entry["destination"] = str(target)
            if check.get("verified"):
                entry["status"] = "VERIFIED"
                verified += 1
            else:
                entry["status"] = "UNVERIFIED"
                entry["warning"] = check.get("reason")
                errors.append(f"{raw_path}: {check.get('reason')}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{raw_path}: {exc}")
            entry["error"] = str(exc)
        results.append(entry)

    return {
        "planned_count": len(raw_paths),
        "executed_count": executed,
        "verified_count": verified,
        "failed_count": len(errors),
        "errors": errors,
        "summary": results,
    }


MAX_WRITE_BYTES = 1024 * 1024  # 1 MB per created/edited file.

# Extensions handled as plain text for creation and editing.
TEXT_EDITABLE_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".jsonl",
    ".log", ".yml", ".yaml", ".xml", ".html", ".htm", ".css",
    ".js", ".ts", ".tsx", ".jsx", ".py", ".sh", ".sql", ".ini",
    ".cfg", ".toml", ".rtf",
}

# Magic numbers enforced when creating binary files (extension -> prefix).
BINARY_MAGIC = {
    ".pdf": (b"%PDF",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".gif": (b"GIF87a", b"GIF89a"),
    ".zip": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    ".docx": (b"PK\x03\x04",),
    ".xlsx": (b"PK\x03\x04",),
    ".pptx": (b"PK\x03\x04",),
}

# Binary formats the editor refuses honestly instead of corrupting.
READ_ONLY_BINARY_EXTENSIONS = {".pdf", ".doc", ".docx", ".ppt", ".pptx"}


def create_directory(conn, *, user_id: int, arguments: dict) -> dict:
    """Create a folder (including parents). Never touches existing files."""
    raw = arguments.get("path")
    if not raw:
        raise ValueError("Parameter path wajib diisi.")
    path = _resolve(raw)
    _protected_guard(path)
    if path.exists() and not path.is_dir():
        raise FileExistsError(f"Sudah ada file dengan nama itu: {path}")
    created = not path.exists()
    path.mkdir(parents=True, exist_ok=True)
    verified = path.is_dir()
    return {
        "executed_count": 1,
        "verified_count": 1 if verified else 0,
        "failed_count": 0 if verified else 1,
        "errors": [] if verified else [f"Folder tidak terbentuk: {path}"],
        "summary": [{"path": str(path), "created": created, "status": "VERIFIED" if verified else "UNVERIFIED"}],
        "path": str(path),
        "created": created,
    }


def _decode_write_content(arguments: dict) -> bytes:
    if "content" not in arguments:
        raise ValueError("Parameter content wajib diisi.")
    content = arguments.get("content") or ""
    encoding = (arguments.get("encoding") or "utf-8").lower()
    if encoding == "base64":
        try:
            data = base64.b64decode(content, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(f"Konten base64 tidak valid: {exc}") from exc
    elif encoding in {"utf-8", "utf8", "text"}:
        data = content.encode("utf-8")
    else:
        raise ValueError("Encoding harus 'utf-8' atau 'base64'.")
    if len(data) > MAX_WRITE_BYTES:
        raise ValueError(f"Konten melebihi batas {MAX_WRITE_BYTES // 1024} KB.")
    return data


def _check_binary_magic(suffix: str, data: bytes) -> str | None:
    """Return a warning when a binary file's magic number looks wrong."""
    prefixes = BINARY_MAGIC.get(suffix)
    if not prefixes:
        return f"Tipe {suffix or 'tanpa ekstensi'} tidak dikenali; isi ditulis apa adanya."
    if not data.startswith(prefixes):
        return f"Isi tidak cocok dengan format {suffix}; file ditulis tapi belum tervalidasi."
    return None


def write_file(conn, *, user_id: int, arguments: dict) -> dict:
    """Create a brand-new file. Refuses to overwrite anything."""
    raw = arguments.get("path")
    if not raw:
        raise ValueError("Parameter path wajib diisi.")
    path = _resolve(raw)
    _protected_guard(path)
    if path.exists():
        raise FileExistsError(f"Sudah ada; file tidak ditimpa: {path}")
    data = _decode_write_content(arguments)
    suffix = path.suffix.lower()
    warning = None
    if suffix not in TEXT_EDITABLE_EXTENSIONS and suffix != "":
        warning = _check_binary_magic(suffix, data)
        if warning is None and suffix == ".zip" and not zipfile.is_zipfile(BytesIO(data)):
            warning = "Isi bukan arsip ZIP yang valid; file ditulis tapi belum tervalidasi."
    if path.parent != path:
        _protected_guard(path.parent)
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    verified = path.exists() and path.stat().st_size == len(data)
    errors = []
    if warning:
        errors.append(warning)
    if not verified:
        errors.append(f"File tidak terbentuk sempurna: {path}")
    return {
        "executed_count": 1,
        "verified_count": 1 if verified else 0,
        "failed_count": 0 if verified else 1,
        "errors": errors,
        "summary": [{"path": str(path), "size": len(data), "status": "VERIFIED" if verified else "UNVERIFIED"}],
        "path": str(path),
        "size": len(data),
    }


def _backup_once(path: Path) -> str | None:
    """Keep one `.bak` copy before the first edit; never overwrite a backup."""
    backup = path.with_name(path.name + ".bak")
    if backup.exists():
        return str(backup)
    shutil.copy2(str(path), str(backup))
    return str(backup)


def _edit_text(path: Path, arguments: dict) -> dict:
    try:
        original = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        raise ValueError(f"File bukan teks UTF-8 yang bisa diubah: {exc}") from exc
    operation = arguments.get("operation") or "replace"
    if operation == "replace":
        old = arguments.get("old")
        new = arguments.get("new", "")
        if old is None or old == "":
            raise ValueError("Parameter old wajib diisi untuk replace.")
        count = arguments.get("count", 1)
        try:
            limit = int(count)
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
        raise ValueError(f"Hasil edit melebihi batas {MAX_WRITE_BYTES // 1024} KB.")
    path.write_text(updated, encoding="utf-8")
    reread = path.read_text(encoding="utf-8")
    return {"changed": changed, "verified": reread == updated}


def _edit_spreadsheet(path: Path, arguments: dict) -> dict:
    try:
        import openpyxl
    except ImportError as exc:
        raise ValueError("Dukungan XLSX belum terpasang di server.") from exc
    sheet_name = arguments.get("sheet")
    cell = arguments.get("cell")
    if not sheet_name or not cell:
        raise ValueError("Parameter sheet dan cell wajib diisi untuk XLSX.")
    if "value" not in arguments:
        raise ValueError("Parameter value wajib diisi untuk XLSX.")
    workbook = openpyxl.load_workbook(str(path))
    if sheet_name not in workbook.sheetnames:
        raise ValueError(f"Sheet tidak ditemukan: {sheet_name}")
    workbook[sheet_name][cell] = arguments.get("value")
    workbook.save(str(path))
    check = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    stored = check[sheet_name][cell].value
    check.close()
    return {"changed": 1, "verified": stored == arguments.get("value")}


def edit_file(conn, *, user_id: int, arguments: dict) -> dict:
    """Edit an existing file. Always keeps one backup; refuses risky formats."""
    raw = arguments.get("path")
    if not raw:
        raise ValueError("Parameter path wajib diisi.")
    path = _resolve(raw)
    _protected_guard(path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"File tidak ditemukan: {path}")
    suffix = path.suffix.lower()
    if suffix in READ_ONLY_BINARY_EXTENSIONS:
        raise ValueError(
            f"Format {suffix} hanya bisa dibaca, belum bisa diubah dengan aman. "
            "Gunakan aplikasi aslinya lalu minta BERESIN memverifikasi hasilnya."
        )
    backup = _backup_once(path)
    if suffix == ".xlsx":
        outcome = _edit_spreadsheet(path, arguments)
    else:
        outcome = _edit_text(path, arguments)
    if not outcome["verified"]:
        errors = ["Hasil edit tidak terverifikasi; backup tersimpan di " + str(backup)]
        verified_count, failed_count = 0, 1
    else:
        errors, verified_count, failed_count = [], 1, 0
    return {
        "executed_count": 1,
        "verified_count": verified_count,
        "failed_count": failed_count,
        "errors": errors,
        "summary": [{
            "path": str(path),
            "backup": str(backup),
            "changed": outcome["changed"],
            "status": "VERIFIED" if outcome["verified"] else "UNVERIFIED",
        }],
        "path": str(path),
        "backup": str(backup),
    }
