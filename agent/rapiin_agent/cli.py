"""RAPIIN Desktop Agent CLI.

Commands:
  rapiin-agent setup [--server URL]   first-run: login + register device
  rapiin-agent run                    poll loop (foreground)
  rapiin-agent status                 show connection/device status
  rapiin-agent autostart [on|off]     manage OS autostart
  rapiin-agent logout                 remove local credentials

PRD sections 9-11: install via terminal, login, register device, manual or
auto start, heartbeat, secure reconnect.
"""
from __future__ import annotations

import argparse
import getpass
import platform
import shlex
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from . import __version__
from .client import AgentAPI
from .config import (
    DEFAULT_SERVER,
    allowed_roots,
    clear_config,
    get_state,
    is_configured,
    load_config,
    save_config,
    set_state,
    update_config_value,
)
from .local_tools import run_tool

POLL_INTERVAL_SECONDS = 3
CAPABILITIES = [
    "filesystem_scanner", "metadata_extractor", "document_parser",
    "duplicate_detector", "file_classifier", "semantic_indexer", "file_search",
    "file_move", "file_copy", "file_rename", "file_delete", "batch_executor", "verification",
    "folder_organizer", "pdf_parser", "spreadsheet_parser", "semantic_search",
    "file_mkdir", "trash_list", "file_restore",
]


def _default_device_name() -> str:
    host = socket.gethostname() or "PC"
    return f"{host}-{platform.system().upper()[:3]}"


def _server_url(value: str | None) -> str:
    if value:
        return value
    cfg = load_config()
    return cfg.get("server_url", DEFAULT_SERVER)


def cmd_setup(args) -> int:
    print("=== Setup RAPIIN Desktop Agent ===")
    server = _server_url(args.server)
    api = AgentAPI(server)

    email = args.email or input("Email: ").strip()
    password = args.password or getpass.getpass("Kata sandi: ")

    try:
        login = api.login(email, password)
    except ConnectionError as exc:
        print(f"[gagal] {exc}", file=sys.stderr)
        return 1
    if login.get("role") != "USER":
        print("[gagal] Akun supervisor tidak dapat dipasang sebagai Desktop Agent.", file=sys.stderr)
        return 1

    device_name = args.device_name or _default_device_name()
    os_name = platform.system() + " " + platform.release()
    requested = getattr(args, "allow_folder", None) or []
    if args.workspace:
        requested.insert(0, args.workspace)
    if not requested:
        requested = [str(Path.home() / name) for name in ("Downloads", "Documents", "Desktop")]
    configured_roots = list(dict.fromkeys(str(Path(p).expanduser().resolve()) for p in requested))
    configured_workspace = configured_roots[0]
    try:
        reg = api.register_device(login["token"], device_name, os_name, __version__, CAPABILITIES, configured_workspace, configured_roots)
    except ConnectionError as exc:
        print(f"[gagal] {exc}", file=sys.stderr)
        return 1

    autostart = args.autostart
    if autostart is None and sys.stdin.isatty():
        choice = input("Mode startup [manual/auto] (manual): ").strip().lower()
        autostart = choice in {"auto", "a", "yes", "y", "ya"}
    autostart = bool(autostart)

    save_config(
        server,
        reg["device_id"],
        reg["device_key"],
        email,
        login["token"],
        startup_mode="auto" if autostart else "manual",
        workspace=configured_workspace,
        allowed_folders=configured_roots,
    )
    print("[ok] Akun terautentikasi")
    print(f"[ok] Perangkat terdaftar: {device_name} (id {reg['device_id']})")
    print("[ok] Koneksi aman ke server")
    print("[ok] RAPIIN Agent siap")

    if autostart:
        _enable_autostart()
    print("\nJalankan 'rapiin' untuk memulai agent (atau aktifkan autostart).")
    return 0


def cmd_folders(args) -> int:
    roots = allowed_roots()
    if args.action == "list":
        print("Folder yang dapat diakses RAPIIN:")
        for root in roots:
            print(f"- {root}")
        return 0
    target = Path(args.path).expanduser().resolve()
    if args.action == "add":
        if not target.is_dir():
            print(f"[gagal] Folder tidak ditemukan: {target}", file=sys.stderr)
            return 2
        if target == Path(target.anchor):
            print("[gagal] Root disk terlalu luas.", file=sys.stderr)
            return 2
        updated = list(dict.fromkeys([*(str(root) for root in roots), str(target)]))
    else:
        updated = [str(root) for root in roots if root != target]
        if not updated:
            print("[gagal] Minimal satu folder harus tetap diizinkan.", file=sys.stderr)
            return 2
    update_config_value("allowed_roots", updated)
    update_config_value("workspace", updated[0])
    print(f"[ok] Daftar folder diperbarui ({len(updated)} folder).")
    return 0


def _handle_job(api: AgentAPI, cfg: dict, job: dict) -> None:
    payload = job.get("payload") or {}
    kind = job.get("kind") or payload.get("tool")
    arguments = payload.get("arguments") or {}
    print(f"[job] {kind} ({job.get('id')})")
    stopped = threading.Event()

    def keep_lease_alive():
        while not stopped.wait(30):
            try:
                api.renew_lease(job["id"], cfg["device_id"], cfg["device_key"])
            except ConnectionError:
                pass

    renewer = threading.Thread(target=keep_lease_alive, daemon=True)
    renewer.start()
    try:
        result = run_tool(kind, arguments)
        api.report(
            job["id"],
            cfg["device_id"],
            cfg["device_key"],
            "SUCCEEDED",
            result={"tool_result": result},
        )
        print(f"[ok] {kind} selesai")
    except Exception as exc:  # noqa: BLE001
        api.report(
            job["id"],
            cfg["device_id"],
            cfg["device_key"],
            "FAILED",
            error=str(exc),
        )
        print(f"[gagal] {kind}: {exc}", file=sys.stderr)
    finally:
        stopped.set()
        renewer.join(timeout=1)


def cmd_run(args) -> int:
    if not is_configured():
        print("Agent belum disetup. Jalankan 'rapiin setup' dulu.", file=sys.stderr)
        return 1
    cfg = load_config()
    api = AgentAPI(cfg["server_url"])
    print(f"RAPIIN Agent {__version__} berjalan untuk {cfg['email']} (device {cfg['device_id']})")
    print("Tekan Ctrl+C untuk berhenti.\n")
    consecutive_errors = 0
    while True:
        try:
            resp = api.poll(cfg["device_id"], cfg["device_key"])
            consecutive_errors = 0
            desired = (resp.get("settings") or {}).get("startup_mode")
            if desired in {"auto", "manual"} and desired != cfg.get("startup_mode"):
                if desired == "auto":
                    _enable_autostart()
                else:
                    _disable_autostart()
                update_config_value("startup_mode", desired)
                cfg["startup_mode"] = desired
            job = resp.get("job")
            if job:
                _handle_job(api, cfg, job)
            else:
                time.sleep(POLL_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print("\nAgent dihentikan.")
            return 0
        except ConnectionError as exc:
            consecutive_errors += 1
            print(f"[!] {exc}", file=sys.stderr)
            delay = min(60, 2 ** min(consecutive_errors, 6))
            print(f"Mencoba tersambung kembali dalam {delay} detik...", file=sys.stderr)
            time.sleep(delay)
        except Exception as exc:  # noqa: BLE001
            print(f"[!] Error tidak terduga: {exc}", file=sys.stderr)
            time.sleep(3)


def cmd_status(args) -> int:
    if not is_configured():
        print("Agent belum disetup.")
        return 0
    cfg = load_config()
    print(f"Server        : {cfg['server_url']}")
    print(f"Email         : {cfg['email']}")
    print(f"Device ID     : {cfg['device_id']}")
    print(f"Startup mode  : {cfg.get('startup_mode', 'unknown')}")
    print(f"Workspace     : {cfg.get('workspace', '-')}")
    print(f"Agent version : {__version__}")
    return 0


def cmd_verify(args) -> int:
    """Verify the device is connected and operational (PRD 9 feedback)."""
    if not is_configured():
        print("[gagal] Agent belum disetup. Jalankan 'rapiin setup' dulu.", file=sys.stderr)
        return 1
    cfg = load_config()
    api = AgentAPI(cfg["server_url"])
    try:
        api.heartbeat(cfg["device_id"], cfg["device_key"])
        print("[ok] Koneksi aman ke server")
    except ConnectionError as exc:
        print(f"[gagal] Tidak dapat terhubung ke server: {exc}", file=sys.stderr)
        return 1

    try:
        resp = api.poll(cfg["device_id"], cfg["device_key"])
        print("[ok] Perangkat terverifikasi (id %s)" % cfg["device_id"])
        print("[ok] Antrean job siap")
    except ConnectionError as exc:
        print(f"[gagal] Polling gagal: {exc}", file=sys.stderr)
        return 1
    print("[ok] RAPIIN Agent siap")
    return 0


def cmd_logout(args) -> int:
    clear_config()
    print("Kredensial lokal dihapus.")
    return 0


def _autostart_paths():
    """Return possible autostart target paths for this OS (no writes)."""
    from pathlib import Path

    if sys.platform == "darwin":
        return [Path.home() / "Library" / "LaunchAgents" / "com.rapiin.agent.plist"]
    if sys.platform.startswith("linux"):
        return [Path.home() / ".config" / "systemd" / "user" / "rapiin-agent.service"]
    if sys.platform == "win32":
        return [Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "rapiin-agent.cmd"]
    return []


def _autostart_enabled() -> bool:
    return any(p.exists() for p in _autostart_paths())


def _agent_run_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "run"]
    return [sys.executable, "-m", "rapiin_agent.cli", "run"]


def _launch_agent_plist():
    from pathlib import Path

    plist_dir = Path.home() / "Library" / "LaunchAgents"
    plist_dir.mkdir(parents=True, exist_ok=True)
    plist = plist_dir / "com.rapiin.agent.plist"
    arguments = "".join(f"<string>{xml_escape(part)}</string>" for part in _agent_run_command())
    plist.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.rapiin.agent</string>
  <key>ProgramArguments</key>
  <array>{arguments}</array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict></plist>
"""
    )
    return plist


def _systemd_service():
    from pathlib import Path

    service_dir = Path.home() / ".config" / "systemd" / "user"
    service_dir.mkdir(parents=True, exist_ok=True)
    svc = service_dir / "rapiin-agent.service"
    command = " ".join(shlex.quote(part) for part in _agent_run_command())
    svc.write_text(
        f"""[Unit]
Description=RAPIIN Desktop Agent
After=network.target

[Service]
ExecStart={command}
Restart=always

[Install]
WantedBy=default.target
"""
    )
    return svc


def _enable_autostart() -> None:
    try:
        if sys.platform == "darwin":
            target = _launch_agent_plist()
            import subprocess

            subprocess.run(["launchctl", "load", str(target)], check=False)
            print("[ok] Autostart aktif (macOS LaunchAgent)")
        elif sys.platform.startswith("linux"):
            target = _systemd_service()
            import subprocess

            subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
            subprocess.run(["systemctl", "--user", "enable", "--now", "rapiin-agent.service"], check=False)
            print("[ok] Autostart aktif (systemd user service)")
        elif sys.platform == "win32":
            import subprocess

            startup = __import__("pathlib").Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
            startup.mkdir(parents=True, exist_ok=True)
            command = subprocess.list2cmdline(_agent_run_command())
            (startup / "rapiin-agent.cmd").write_text(f"@echo off\n{command}\n")
            print("[ok] Autostart aktif (Windows Startup folder)")
    except Exception as exc:  # noqa: BLE001
        print(f"[!] Gagal mengaktifkan autostart: {exc}", file=sys.stderr)


def _disable_autostart() -> None:
    """Unload/disable the service and remove only RAPIIN's exact startup file."""
    import subprocess
    targets = _autostart_paths()
    try:
        if sys.platform == "darwin" and targets:
            subprocess.run(["launchctl", "unload", str(targets[0])], check=False)
        elif sys.platform.startswith("linux"):
            subprocess.run(["systemctl", "--user", "disable", "--now", "rapiin-agent.service"], check=False)
        for target in targets:
            if target.exists() and target.is_file():
                target.unlink()
        print("[ok] Autostart nonaktif")
    except Exception as exc:
        print(f"[!] Gagal menonaktifkan autostart: {exc}", file=sys.stderr)


def cmd_autostart(args) -> int:
    if args.enable is None:
        print("Autostart saat ini:", "aktif" if _autostart_enabled() else "tidak aktif")
        return 0
    if args.enable:
        _enable_autostart()
    else:
        _disable_autostart()
    return 0


def cmd_upgrade(args) -> int:
    wheel = Path(args.wheel).expanduser().resolve()
    if not wheel.is_file() or wheel.suffix != ".whl" or "rapiin_agent-" not in wheel.name:
        print("[gagal] Gunakan wheel RAPIIN Agent yang valid.", file=sys.stderr)
        return 2
    uv = shutil.which("uv")
    if uv:
        command = [uv, "pip", "install", "--python", sys.executable, "--upgrade", "--no-deps", str(wheel)]
    else:
        command = [sys.executable, "-m", "pip", "install", "--upgrade", "--no-deps", str(wheel)]
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        print("[gagal] Upgrade tidak berhasil; instalasi lama dipertahankan oleh pip.", file=sys.stderr)
        return completed.returncode
    print(f"[ok] RAPIIN Agent diperbarui dari {wheel.name}")
    return 0


def cmd_uninstall(args) -> int:
    _disable_autostart()
    if not args.keep_config:
        clear_config()
        print("[ok] Kredensial dan state lokal RAPIIN dihapus")
    if shutil.which("uv"):
        print("Hapus paket dengan: uv tool uninstall rapiin-agent")
    else:
        print(f"Hapus paket dengan: {sys.executable} -m pip uninstall rapiin-agent")
    return 0


def _boot_identifier() -> str:
    try:
        if sys.platform.startswith("linux"):
            return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        if sys.platform == "darwin":
            return subprocess.run(["sysctl", "-n", "kern.boottime"], capture_output=True, text=True, check=True).stdout.strip()
        if sys.platform == "win32":
            return subprocess.run(
                ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToFileTimeUtc()"],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
    except Exception:
        return ""
    return ""


def cmd_startup_probe(args) -> int:
    boot_id = _boot_identifier()
    if not boot_id:
        print("[gagal] Identitas boot OS tidak dapat dibaca.", file=sys.stderr)
        return 2
    if args.action == "record":
        set_state("startup_probe_boot_id", boot_id)
        set_state("startup_probe_recorded_at", time.time())
        print("[ok] Baseline boot direkam. Reboot komputer lalu jalankan startup-probe verify.")
        return 0
    previous = get_state("startup_probe_boot_id")
    if not previous:
        print("[gagal] Belum ada baseline. Jalankan startup-probe record sebelum reboot.", file=sys.stderr)
        return 2
    if previous == boot_id:
        print("[gagal] Reboot belum terbukti; boot identifier masih sama.", file=sys.stderr)
        return 3
    if not _autostart_enabled():
        print("[gagal] Komputer reboot tetapi konfigurasi autostart tidak ditemukan.", file=sys.stderr)
        return 4
    print("[ok] Reboot dan keberadaan konfigurasi autostart terverifikasi.")
    return cmd_verify(args)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rapiin", description="RAPIIN Desktop Agent")
    sub = parser.add_subparsers(dest="command")

    p_setup = sub.add_parser("setup", help="first-run setup (login + register device)")
    p_setup.add_argument("--server", default=None, help="server URL")
    p_setup.add_argument("--email", default=None)
    p_setup.add_argument("--password", default=None)
    p_setup.add_argument("--device-name", default=None)
    p_setup.add_argument("--workspace", default=None, help="folder yang boleh diubah agent (default ~/Downloads)")
    p_setup.add_argument("--allow-folder", action="append", default=[], help="folder tambahan; dapat diulang")
    p_setup.add_argument("--autostart", action=argparse.BooleanOptionalAction, default=None, help="aktifkan autostart setelah setup")

    sub.add_parser("run", help="jalankan agent (poll loop)")
    sub.add_parser("status", help="tampilkan status agent")
    sub.add_parser("verify", help="verifikasi perangkat & koneksi ke server")
    p_auto = sub.add_parser("autostart", help="kelola autostart")
    p_auto.add_argument("state", nargs="?", choices=["on", "off"], default=None)
    sub.add_parser("logout", help="hapus kredensial lokal")
    p_upgrade = sub.add_parser("upgrade", help="upgrade dari wheel rilis yang sudah diverifikasi")
    p_upgrade.add_argument("--wheel", required=True, help="path wheel rapiin_agent")
    p_uninstall = sub.add_parser("uninstall", help="nonaktifkan service dan siapkan penghapusan agent")
    p_uninstall.add_argument("--keep-config", action="store_true", help="pertahankan konfigurasi lokal")
    p_probe = sub.add_parser("startup-probe", help="buktikan autostart melewati reboot OS nyata")
    p_probe.add_argument("action", choices=["record", "verify"])
    p_folders = sub.add_parser("folders", help="lihat/tambah/hapus folder yang dapat diakses")
    p_folders.add_argument("action", choices=["list", "add", "remove"])
    p_folders.add_argument("path", nargs="?")

    args = parser.parse_args(argv)
    if args.command is None:
        if is_configured():
            return cmd_run(args)
        print("RAPIIN belum dikonfigurasi; memulai first-run setup.\n")
        return cmd_setup(argparse.Namespace(
            server=None, email=None, password=None, device_name=None,
            workspace=None, allow_folder=[], autostart=None,
        ))
    if args.command == "setup":
        return cmd_setup(args)
    if args.command == "run":
        return cmd_run(args)
    if args.command == "status":
        return cmd_status(args)
    if args.command == "verify":
        return cmd_verify(args)
    if args.command == "autostart":
        args.enable = True if args.state == "on" else False if args.state == "off" else None
        return cmd_autostart(args)
    if args.command == "logout":
        return cmd_logout(args)
    if args.command == "upgrade":
        return cmd_upgrade(args)
    if args.command == "uninstall":
        return cmd_uninstall(args)
    if args.command == "startup-probe":
        return cmd_startup_probe(args)
    if args.command == "folders":
        if args.action != "list" and not args.path:
            parser.error("folders add/remove memerlukan path")
        return cmd_folders(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
