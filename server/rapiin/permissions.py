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

# Actions that never require approval (read / analysis / search, plus
# creating empty folders inside the sandbox)
AUTO_ACTIONS = {
    "filesystem_scanner", "metadata_extractor", "file_search", "duplicate_detector",
    "document_parser", "pdf_parser", "spreadsheet_parser", "verification",
    "file_classifier", "semantic_indexer", "semantic_search", "file_mkdir",
    "trash_list", "file_restore",
}

# Tools that change files. In the default flow they are gated by an approval
# and then executed on the device; in FULL_AUTO they still run on the device
# (that is where the files are), but without a card.
MUTATION_ACTIONS = {
    "file_move", "file_copy", "file_rename", "file_delete", "file_mkdir",
    "file_write", "file_edit", "batch_executor", "bulk_delete",
}

# Actions that require user approval
USER_APPROVAL_ACTIONS = {"file_move", "file_rename", "file_copy", "file_write", "file_edit"}

# Destructive / bulk actions require stronger (supervisor) approval
SUPERVISOR_APPROVAL_ACTIONS = {"file_delete", "batch_executor", "bulk_delete"}

# Actions that destroy data without a recoverable copy. Under FULL_AUTO these
# are routed through the trash ledger so the user can still undo them.
DESTRUCTIVE_ACTIONS = {"file_delete", "bulk_delete", "batch_executor"}

# Explicit opt-out mode: every tool, including destructive ones, runs without
# an approval card. The user must choose this themselves; it is never a default.
FULL_AUTO = "FULL_AUTO"
POLICY_KINDS = {"AUTO", "USER", "SUPERVISOR"}

# Environment variable to locate the sandbox root when present.
_DEFAULT_ROOT_CANDIDATES = [
    os.environ.get("RAPIIN_SANDBOX_ROOT"),
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
    def __init__(
        self,
        role: str = "USER",
        policies: dict[str, dict] | None = None,
        user_policies: dict[str, dict] | None = None,
        full_auto: bool = False,
    ):
        self.role = role
        self.policies = policies or {}
        self.user_policies = user_policies or {}
        self.full_auto = bool(full_auto)

    @classmethod
    def from_db(cls, conn, role: str = "USER", user_id: int | None = None):
        """Load the effective policy set for a user.

        Resolution order (highest wins): the user's own row in
        ``user_action_policies`` -> the global ``action_policies`` row -> the
        built-in default. FULL_AUTO is a user-level switch that bypasses the
        per-tool decision entirely.
        """
        rows = conn.execute(
            "SELECT tool_name, approval_kind, bulk_threshold FROM action_policies"
        ).fetchall()
        policies = {row["tool_name"]: dict(row) for row in rows}
        user_policies: dict[str, dict] = {}
        full_auto = False
        if user_id is not None:
            user_rows = conn.execute(
                "SELECT tool_name, approval_kind FROM user_action_policies WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            user_policies = {row["tool_name"]: dict(row) for row in user_rows}
            flag = conn.execute(
                "SELECT full_auto_mode FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if flag:
                try:
                    full_auto = bool(flag["full_auto_mode"])
                except (KeyError, IndexError, TypeError):
                    full_auto = False
        return cls(role=role, policies=policies, user_policies=user_policies, full_auto=full_auto)

    def configured_kind(self, tool_name: str) -> tuple[str | None, str]:
        """Return (kind, source) for a tool from user/global config only."""
        if tool_name in self.user_policies:
            return self.user_policies[tool_name]["approval_kind"], "user"
        if tool_name in self.policies:
            return self.policies[tool_name]["approval_kind"], "global"
        return None, "default"

    def default_kind(self, tool_name: str) -> str:
        if tool_name in AUTO_ACTIONS:
            return "AUTO"
        if tool_name in SUPERVISOR_APPROVAL_ACTIONS:
            return "SUPERVISOR"
        if tool_name in USER_APPROVAL_ACTIONS:
            return "USER"
        return "AUTO"

    def effective_kind(self, tool_name: str) -> str:
        """The approval kind actually in force, including FULL_AUTO."""
        if self.full_auto:
            return FULL_AUTO
        kind, _ = self.configured_kind(tool_name)
        return kind or self.default_kind(tool_name)

    def action_approval_kind(self, tool_name: str, *, count: int = 1) -> str | None:
        """Return required approval kind: 'USER', 'SUPERVISOR', or None (auto)."""
        if self.full_auto:
            # The user explicitly chose to run everything without approval.
            return None
        kind, source = self.configured_kind(tool_name)
        threshold = int(self.policies.get(tool_name, {}).get("bulk_threshold") or 20)
        if kind is not None:
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
