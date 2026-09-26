"""Reversible trash for destructive operations run without an approval.

When a user enables FULL_AUTO there is no approval card to catch a mistake, so
every delete must be recoverable. Instead of unlinking a file, the agent moves
it under ``<root>/.rapiin-trash/<trash-id>/`` and writes a manifest describing
where each item came from. ``restore_trash`` reads that manifest and puts the
items back.

The trash folder is hidden (leading dot) so scans skip it, and it always lives
inside an allowed root, so the sandbox rules still apply.
"""
from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path

TRASH_DIR_NAME = ".rapiin-trash"


def _is_relative_to(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _allowed_roots() -> list[Path]:
    from .config import allowed_roots

    return [root.resolve() for root in allowed_roots()]


def _root_for(path: Path) -> Path:
    """Pick the allowed root that contains ``path`` (first root as fallback)."""
    resolved = path.expanduser().resolve()
    for root in _allowed_roots():
        if _is_relative_to(resolved, root):
            return root
    return _allowed_roots()[0]


def _new_trash_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]


def _unique_destination(folder: Path, name: str) -> Path:
    candidate = folder / name
    if not candidate.exists():
        return candidate
    stem, suffix = Path(name).stem, Path(name).suffix
    index = 1
    while True:
        candidate = folder / f"{stem}__{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def trash_paths(paths: list[str], *, note: str = "") -> dict:
    """Move each path into a fresh trash folder and record a manifest.

    Returns a result shaped like the other mutation tools so the server can
    persist it unchanged.
    """
    if not paths:
        return {"status": "ERROR", "message": "Tidak ada file untuk dipindahkan ke trash."}

    resolved = [Path(p).expanduser() for p in paths]
    base_root = _root_for(resolved[0])
    trash_id = _new_trash_id()
    trash_dir = base_root / TRASH_DIR_NAME / trash_id

    results: list[dict] = []
    errors: list[str] = []
    executed = verified = 0
    manifest_items: list[dict] = []
    try:
        trash_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {"status": "ERROR", "message": f"Tidak dapat membuat folder trash: {exc}"}

    for source in resolved:
        entry: dict = {"path": str(source), "status": "FAILED"}
        try:
            if not source.exists():
                raise FileNotFoundError(f"File tidak ditemukan: {source}")
            destination = _unique_destination(trash_dir, source.name)
            shutil.move(str(source), str(destination))
            executed += 1
            if not source.exists() and destination.exists():
                verified += 1
                entry["status"] = "TRASHED"
                entry["trashed_to"] = str(destination)
                manifest_items.append({
                    "original": str(source),
                    "trashed": str(destination),
                    "name": source.name,
                    "is_dir": destination.is_dir(),
                })
            else:
                errors.append(f"{source}: verifikasi trash gagal")
                entry["status"] = "UNVERIFIED"
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{source}: {exc}")
            entry["error"] = str(exc)
        results.append(entry)

    manifest = {
        "id": trash_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "root": str(base_root),
        "note": note,
        "item_count": len(manifest_items),
        "items": manifest_items,
    }
    manifest_path = trash_dir / "manifest.json"
    try:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        errors.append(f"manifest: {exc}")

    if not manifest_items:
        # Nothing moved: remove the empty folder so the user sees no ghost entry.
        try:
            trash_dir.rmdir()
        except OSError:
            pass

    overall = "ERROR" if executed == 0 and errors else ("PARTIAL" if errors else "OK")
    return {
        "status": overall,
        "reversible": True,
        "trash_id": trash_id if manifest_items else None,
        "trash_dir": str(trash_dir) if manifest_items else None,
        "planned_count": len(resolved),
        "executed_count": executed,
        "verified_count": verified,
        "failed_count": len(errors),
        "errors": errors,
        "summary": results,
    }


def _trash_manifests() -> list[tuple[Path, dict]]:
    found: list[tuple[Path, dict]] = []
    for root in _allowed_roots():
        base = root / TRASH_DIR_NAME
        if not base.is_dir():
            continue
        for manifest_path in sorted(base.glob("*/manifest.json")):
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            found.append((manifest_path, data))
    return found


def list_trash() -> dict:
    """List recoverable trash batches, newest first."""
    entries = []
    for _, data in _trash_manifests():
        entries.append({
            "id": data.get("id"),
            "created_at": data.get("created_at"),
            "item_count": data.get("item_count", 0),
            "root": data.get("root"),
        })
    entries.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return {"status": "OK", "count": len(entries), "entries": entries}


def _find_manifest(trash_id: str) -> tuple[Path, dict] | None:
    for manifest_path, data in _trash_manifests():
        if str(data.get("id")) == str(trash_id):
            return manifest_path, data
    return None


def restore_trash(trash_id: str) -> dict:
    """Move a whole trash batch back to its original locations."""
    if not trash_id:
        return {"status": "ERROR", "message": "Parameter trash_id wajib."}
    found = _find_manifest(trash_id)
    if not found:
        return {"status": "ERROR", "message": f"Trash '{trash_id}' tidak ditemukan."}
    manifest_path, data = found
    trash_dir = manifest_path.parent

    results: list[dict] = []
    errors: list[str] = []
    restored = skipped = 0
    for item in data.get("items", []):
        original = Path(str(item.get("original", "")))
        trashed = Path(str(item.get("trashed", "")))
        entry: dict = {"original": str(original), "status": "FAILED"}
        try:
            if not trashed.exists():
                entry["status"] = "MISSING"
                entry["error"] = "Item sudah tidak ada di trash."
                results.append(entry)
                continue
            if original.exists():
                entry["status"] = "SKIPPED"
                entry["error"] = "Sudah ada file di lokasi asal; tidak ditimpa."
                skipped += 1
                results.append(entry)
                continue
            original.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(trashed), str(original))
            if original.exists() and not trashed.exists():
                restored += 1
                entry["status"] = "RESTORED"
            else:
                errors.append(f"{original}: verifikasi restore gagal")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{original}: {exc}")
            entry["error"] = str(exc)
        results.append(entry)

    # Drop the batch folder when everything is back; keep it if items remain.
    remaining = [p for p in trash_dir.rglob("*") if p.is_file() and p.name != "manifest.json"]
    if not remaining:
        try:
            shutil.rmtree(trash_dir)
        except OSError:
            pass

    return {
        "status": "OK" if not errors else ("PARTIAL" if restored else "ERROR"),
        "trash_id": trash_id,
        "restored_count": restored,
        "skipped_count": skipped,
        "failed_count": len(errors),
        "errors": errors,
        "summary": results,
    }
