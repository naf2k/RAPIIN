"""Permission Engine - capability and policy checks.

Default policy follows PRD section 17:
- read / analyze / search are automatic
- rename / copy are policy controlled
- move requires approval depending on scope
- delete requires approval
- bulk delete requires stronger (supervisor) approval
- protected paths are blocked
- other users data is blocked
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Capabilities per PRD
CAP_READ_FILES = "READ_FILES"
CAP_SCAN_FILES = "SCAN_FILES"
CAP_SEARCH_FILES = "SEARCH_FILES"
CAP_MOVE_FILES = "MOVE_FILES"
CAP_COPY_FILES = "COPY_FILES"
CAP_RENAME_FILES = "RENAME_FILES"
CAP_DELETE_FILES = "DELETE_FILES"
CAP_BULK_OPERATION = "BULK_OPERATION"

AUTO_CAPABILITIES = {CAP_READ_FILES, CAP_SCAN_FILES, CAP_SEARCH_FILES}

# Actions that never require approval (read / analysis / search)
AUTO_ACTIONS = {
    "filesystem_scanner", "metadata_extractor", "file_search", "duplicate_detector",
    "document_parser", "pdf_parser", "spreadsheet_parser", "verification",
    "file_classifier", "semantic_indexer", "semantic_search",
}

# Actions that require user approval
USER_APPROVAL_ACTIONS = {"file_move", "file_rename", "file_copy"}

# Destructive / bulk actions require stronger (supervisor) approval
SUPERVISOR_APPROVAL_ACTIONS = {"file_delete", "batch_executor", "bulk_delete"}

# Environment variable to locate the sandbox root when present.
_DEFAULT_ROOT_CANDIDATES = [
    os.environ.get("BERESIN_SANDBOX_ROOT"),
    str(Path.home() / "Downloads"),
    str(Path.home()),
    ".",
]


def sandbox_root() -> Path:
    for candidate in _DEFAULT_ROOT_CANDIDATES:
        if candidate:
            try:
                root = Path(candidate).expanduser().resolve()
                if root.exists():
                    return root
            except Exception:
                continue
    return Path(".").resolve()


# Directories that are never touched.
def _is_protected(path: Path) -> bool:
    parts = path.resolve().parts
    lower_parts = {p.lower() for p in parts}
    protected_names = {
        "windows", "program files", "program files (x86)", "system32",
        "library", "etc", "bin", "sbin", "usr", "var", "private",
        "applications", "node_modules", ".git", ".commandcode",
    }
    return bool(lower_parts & protected_names)


def resolve_path(root: Path, raw: str) -> Path:
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = root / p
    return p.resolve()


def check_path_allowed(root: Path, raw: str) -> tuple[bool, str]:
    """Return (allowed, reason)."""
    try:
        path = resolve_path(root, raw)
    except Exception as exc:
        return False, f"Path tidak valid: {exc}"
    try:
        path.relative_to(root)
    except ValueError:
        return False, "Path berada di luar cakupan yang diizinkan."
    if _is_protected(path):
        return False, "Path dilindungi sistem."
    return True, ""


class PermissionEngine:
    def __init__(self, role: str = "USER", policies: dict[str, dict] | None = None):
        self.role = role
        self.policies = policies or {}

    @classmethod
    def from_db(cls, conn, role: str = "USER"):
        rows = conn.execute("SELECT tool_name, approval_kind, bulk_threshold FROM action_policies").fetchall()
        return cls(role=role, policies={row["tool_name"]: dict(row) for row in rows})

    def action_approval_kind(self, tool_name: str, *, count: int = 1) -> str | None:
        """Return required approval kind: 'USER', 'SUPERVISOR', or None (auto)."""
        configured = self.policies.get(tool_name)
        if configured:
            kind = configured["approval_kind"]
            threshold = int(configured.get("bulk_threshold") or 20)
            if count > threshold and kind == "USER":
                return "SUPERVISOR"
            return None if kind == "AUTO" else kind
        if tool_name in AUTO_ACTIONS:
            return None
        if tool_name in SUPERVISOR_APPROVAL_ACTIONS:
            if tool_name in {"batch_executor", "bulk_delete"} or count > 20:
                return "SUPERVISOR"
            return "USER"
        if tool_name in USER_APPROVAL_ACTIONS:
            return "USER"
        return None

    def requires_approval(self, tool_name: str, *, count: int = 1) -> bool:
        return self.action_approval_kind(tool_name, count=count) is not None

    def can(self, capability: str) -> bool:
        if capability in AUTO_CAPABILITIES:
            return True
        if capability in {CAP_DELETE_FILES, CAP_BULK_OPERATION}:
            return False  # always gated by approval flow
        return True  # policy-controlled capabilities allowed after approval
