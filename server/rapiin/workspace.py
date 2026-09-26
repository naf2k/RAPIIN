"""Device workspace path resolution.

The server must never invent a filesystem path for a user's device. Every
delegated tool call is anchored to the workspace a device registered at setup
time (``devices.workspace_root`` / ``devices.allowed_roots``). A path that ends
up outside those roots is refused before a job is queued, so a wrong or stale
path can never reach the employee's machine.

The Desktop Agent enforces the same roots locally before touching a file, so
this module is the server-side half of a fail-closed pair.
"""
from __future__ import annotations

import json
import os

# Argument keys that carry a filesystem path in a tool payload.
PATH_KEYS = ("path", "source", "destination", "target", "directory")
PATH_LIST_KEYS = ("paths", "files")


class WorkspaceViolation(Exception):
    """A tool path fell outside the device's registered roots."""


def device_roots(conn, device_id: int | None) -> list[str]:
    """Return the registered allowed roots for a device.

    ``workspace_root`` is included as a fallback for devices registered before
    multi-folder access existed, mirroring the Desktop Agent's own behaviour.
    """
    if not device_id:
        return []
    row = conn.execute(
        "SELECT workspace_root, allowed_roots FROM devices WHERE id = ?", (device_id,)
    ).fetchone()
    if not row:
        return []
    try:
        roots = json.loads(row["allowed_roots"] or "[]")
    except (TypeError, json.JSONDecodeError):
        roots = []
    if not isinstance(roots, list):
        roots = []
    if not roots and row["workspace_root"]:
        roots = [row["workspace_root"]]
    return [str(root) for root in roots if root]


def _normalize(raw: str) -> str:
    return os.path.normpath(os.path.expanduser(str(raw)))


def _within(path: str, root: str) -> bool:
    candidate = _normalize(path)
    boundary = _normalize(root)
    if candidate == boundary or candidate.startswith(boundary.rstrip("/") + "/"):
        return True
    # Fall back to a symlink-resolved comparison (/tmp vs /private/tmp on macOS).
    real_candidate = os.path.realpath(candidate)
    real_boundary = os.path.realpath(boundary)
    return real_candidate == real_boundary or real_candidate.startswith(real_boundary.rstrip("/") + "/")


def path_within(path: str, roots: list[str]) -> bool:
    if not roots:
        return False
    return any(_within(path, root) for root in roots)


def _match_root_by_name(roots: list[str], name: str) -> str | None:
    """Return a registered root whose final segment equals ``name``."""
    if not name:
        return None
    for root in sorted(roots, key=len, reverse=True):
        parts = [part for part in _normalize(root).strip("/").split("/") if part]
        if parts and parts[-1] == name:
            return root
    return None


def _ground_one(raw: str, roots: list[str]) -> str:
    path = _normalize(raw)
    if os.path.isabs(path):
        if path_within(path, roots):
            return path
        # A stale or foreign absolute path whose last segment names a
        # registered root: the user meant that folder itself, not a child.
        base = _match_root_by_name(roots, os.path.basename(path))
        if base is not None:
            return base
        return path  # left untouched; validation rejects it explicitly

    parts = [part for part in path.split(os.sep) if part]
    if parts:
        base = _match_root_by_name(roots, parts[0])
        if base is not None:
            return os.path.join(base, *parts[1:]) if len(parts) > 1 else base
    if not path or path == ".":
        return roots[0]
    # A relative child path is anchored to the workspace root (first root).
    return os.path.join(roots[0], path)


def _base_folder_for_lists(grounded: dict, roots: list[str]) -> str | None:
    """Find the folder that relative ``paths``/``files`` entries are under.

    Models often send ``source`` (a folder) together with bare filenames in
    ``paths``. Anchoring those names to the workspace root would invent a path
    that does not exist, so the folder from ``source``/``directory`` wins when
    it resolves inside the allowed roots.
    """
    for key in ("source", "directory"):
        value = grounded.get(key)
        if isinstance(value, str) and value:
            candidate = _normalize(value)
            if path_within(candidate, roots) and os.path.isdir(candidate):
                return candidate
    return None


def ground_arguments(arguments: dict, roots: list[str]) -> dict:
    """Return a copy with missing/relative/stale paths anchored to a root."""
    if not roots or not arguments:
        return dict(arguments or {})
    grounded = dict(arguments)
    for key in PATH_KEYS:
        value = grounded.get(key)
        if isinstance(value, str) and value:
            grounded[key] = _ground_one(value, roots)
    base = _base_folder_for_lists(grounded, roots)
    for key in PATH_LIST_KEYS:
        value = grounded.get(key)
        if isinstance(value, list):
            rewritten = []
            for item in value:
                if not item:
                    rewritten.append(item)
                    continue
                original = str(item)
                grounded_item = _ground_one(original, roots)
                # A bare filename listed next to its folder belongs to that
                # folder, not to the workspace root.
                if base is not None and not os.path.isabs(original):
                    grounded_item = os.path.join(base, os.path.basename(original.lstrip("./")))
                rewritten.append(grounded_item)
            grounded[key] = rewritten
    return grounded


def validate_arguments(arguments: dict, roots: list[str]) -> str | None:
    """Return a rejection reason if any path escapes the device roots."""
    candidates: list[str] = []
    for key in PATH_KEYS:
        value = (arguments or {}).get(key)
        if isinstance(value, str) and value:
            candidates.append(value)
    for key in PATH_LIST_KEYS:
        value = (arguments or {}).get(key)
        if isinstance(value, list):
            candidates.extend(str(item) for item in value if item)
    for raw in candidates:
        if not path_within(raw, roots):
            shown = ", ".join(roots)
            return f"Path '{raw}' di luar folder yang diizinkan perangkat ({shown})."
    return None


def ground_and_validate(conn, device_id: int | None, arguments: dict) -> dict:
    """Anchor a tool payload to the device workspace, raising on escape.

    When the device has no registered roots (e.g. a device-less task) the
    payload is returned unchanged; the caller keeps its previous behaviour.
    """
    roots = device_roots(conn, device_id)
    if not roots:
        return dict(arguments or {})
    grounded = ground_arguments(arguments, roots)
    reason = validate_arguments(grounded, roots)
    if reason:
        raise WorkspaceViolation(reason)
    return grounded
