"""Filesystem tools - scanning, metadata, search and mutation within a sandbox."""
from __future__ import annotations

import shutil
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
