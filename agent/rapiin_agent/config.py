"""Agent configuration and credential storage.

Credentials (server URL, device key, session token) live in a user-owned
config file. Sensitive fields (device_key, token) are encrypted at rest with
Fernet using a key derived from this machine's identity, so copying the file
to another computer does not leak usable credentials (PRD 26).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

try:
    from cryptography.fernet import Fernet, InvalidToken
except Exception:  # pragma: no cover
    Fernet = None
    InvalidToken = Exception

if sys.platform == "win32":
    CONFIG_DIR = Path.home() / "AppData" / "Local" / "RAPIIN"
else:
    CONFIG_DIR = Path.home() / ".rapiin"

CONFIG_FILE = CONFIG_DIR / "config.json"
STATE_FILE = CONFIG_DIR / "state.json"

DEFAULT_SERVER = "http://127.0.0.1:8000"

SECRET_FIELDS = {"device_key", "token"}
KEYRING_SERVICE = "RAPIIN Desktop Agent"


def workspace_root() -> Path:
    """Directory the agent may mutate. Configured at setup or defaults to
    the user's Downloads folder (main V1 use case)."""
    cfg = _load(CONFIG_FILE)
    raw = cfg.get("workspace")
    if raw:
        p = Path(raw).expanduser()
        try:
            p.mkdir(parents=True, exist_ok=True)
            return p.resolve()
        except Exception:
            pass
    default = Path.home() / "Downloads"
    try:
        default.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return default


def allowed_roots() -> list[Path]:
    """Folders explicitly available to every filesystem tool.

    ``workspace`` remains supported for agents configured before multi-folder
    access was introduced. New configurations store ``allowed_roots``.
    """
    cfg = _load(CONFIG_FILE)
    raw_roots = cfg.get("allowed_roots")
    if not isinstance(raw_roots, list) or not raw_roots:
        return [workspace_root().resolve()]
    roots: list[Path] = []
    for raw in raw_roots:
        try:
            root = Path(str(raw)).expanduser().resolve()
        except (OSError, RuntimeError):
            continue
        if root not in roots:
            roots.append(root)
    return roots or [workspace_root().resolve()]


def _machine_identity() -> str:
    """A stable per-machine secret used to derive the encryption key."""
    candidates = []
    try:
        if sys.platform == "darwin":
            out = subprocess.run(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True, text=True, timeout=5,
            ).stdout
            for line in out.splitlines():
                if "IOPlatformUUID" in line:
                    candidates.append(line.split('"')[-2])
                    break
        elif sys.platform.startswith("linux"):
            p = Path("/etc/machine-id")
            if p.exists():
                candidates.append(p.read_text().strip())
        elif sys.platform == "win32":
            out = subprocess.run(
                ["reg", "query", r"HKLM\SOFTWARE\Microsoft\Cryptography", "/v", "MachineGuid"],
                capture_output=True, text=True, timeout=5,
            ).stdout
            candidates.append(out)
    except Exception:
        pass
    candidates.append(str(Path.home()))  # fallback: home dir path
    return "|".join(candidates)


def _fernet() -> "Fernet | None":
    if Fernet is None:
        return None
    digest = hashlib.sha256(_machine_identity().encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def _encrypt(value: str) -> str:
    f = _fernet()
    if f is None:
        return value
    return "enc:" + f.encrypt(value.encode("utf-8")).decode("ascii")


def _decrypt(value: str) -> str:
    if not value.startswith("enc:"):
        return value
    f = _fernet()
    if f is None:
        return value
    try:
        return f.decrypt(value[4:].encode("ascii")).decode("utf-8")
    except InvalidToken:
        return ""


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(path: Path, data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        CONFIG_DIR.chmod(0o700)
    except OSError:
        pass
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _store_secret(field: str, value: str) -> str:
    """Prefer the operating-system credential vault, with encrypted fallback."""
    try:
        import keyring
        keyring.set_password(KEYRING_SERVICE, field, value)
        if keyring.get_password(KEYRING_SERVICE, field) == value:
            return "keyring:" + field
    except Exception:
        pass
    encrypted = _encrypt(value)
    if not encrypted.startswith("enc:"):
        raise RuntimeError("Penyimpanan kredensial aman tidak tersedia.")
    return encrypted


def _read_secret(field: str, stored: str) -> str:
    if stored.startswith("keyring:"):
        try:
            import keyring
            return keyring.get_password(KEYRING_SERVICE, stored[8:]) or ""
        except Exception:
            return ""
    return _decrypt(stored)


def save_config(
    server_url: str,
    device_id: int,
    device_key: str,
    email: str,
    token: str,
    startup_mode: str = "manual",
    workspace: str | None = None,
    allowed_folders: list[str] | None = None,
) -> None:
    data = {
        "server_url": server_url.rstrip("/"),
        "device_id": device_id,
        "device_key": _store_secret("device_key", device_key),
        "email": email,
        "token": _store_secret("token", token),
        "startup_mode": startup_mode,
    }
    if workspace:
        data["workspace"] = workspace
    if allowed_folders:
        data["allowed_roots"] = allowed_folders
    _save(CONFIG_FILE, data)


def load_config(decrypt_secrets: bool = True) -> dict:
    cfg = _load(CONFIG_FILE)
    if decrypt_secrets:
        for field in SECRET_FIELDS:
            if cfg.get(field):
                cfg[field] = _read_secret(field, cfg[field])
    return cfg


def clear_config() -> None:
    try:
        import keyring
        for field in SECRET_FIELDS:
            try:
                keyring.delete_password(KEYRING_SERVICE, field)
            except Exception:
                pass
    except Exception:
        pass
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()
    if STATE_FILE.exists():
        STATE_FILE.unlink()


def update_config_value(key: str, value) -> None:
    cfg = _load(CONFIG_FILE)
    cfg[key] = value
    _save(CONFIG_FILE, cfg)


def set_state(key: str, value) -> None:
    state = _load(STATE_FILE)
    state[key] = value
    _save(STATE_FILE, state)


def get_state(key: str, default=None):
    return _load(STATE_FILE).get(key, default)


def is_configured() -> bool:
    cfg = load_config()
    return bool(cfg.get("server_url") and cfg.get("device_key") and cfg.get("device_id"))
