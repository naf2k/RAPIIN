import argparse
import json
import os
from pathlib import Path

import pytest

from beresin_agent import cli, config, local_tools


def test_bares_command_starts_setup_on_first_run(monkeypatch):
    monkeypatch.setattr(cli, "is_configured", lambda: False)
    monkeypatch.setattr(cli, "cmd_setup", lambda args: 17 if args.server is None else 0)
    assert cli.main([]) == 17


def test_bares_command_runs_agent_when_configured(monkeypatch):
    monkeypatch.setattr(cli, "is_configured", lambda: True)
    monkeypatch.setattr(cli, "cmd_run", lambda _args: 23)
    assert cli.main([]) == 23


@pytest.mark.parametrize("count", [10, 100])
def test_scan_prd_file_counts(tmp_path, count, monkeypatch):
    monkeypatch.setattr(config, "workspace_root", lambda: tmp_path)
    for index in range(count):
        (tmp_path / f"file-{index}.txt").write_text("data")
    assert local_tools.run_tool("filesystem_scanner", {"path": str(tmp_path)})["file_count"] == count


def test_scan_more_than_one_thousand_files(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "workspace_root", lambda: tmp_path)
    for index in range(1005):
        (tmp_path / f"doc-{index}.txt").write_text("data")
    result = local_tools.run_tool("filesystem_scanner", {"path": str(tmp_path)})
    assert result["status"] == "OK"
    assert result["file_count"] == 1005
    assert result["truncated"] is True
    assert len(result["files"]) == 200


def test_locked_file_is_skipped_without_crashing_duplicate_scan(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "workspace_root", lambda: tmp_path)
    locked = tmp_path / "locked.txt"
    normal = tmp_path / "normal.txt"
    locked.write_text("secret")
    normal.write_text("normal")
    real_hash = local_tools._hash

    def guarded_hash(path):
        if Path(path) == locked:
            raise PermissionError("file terkunci")
        return real_hash(path)

    monkeypatch.setattr(local_tools, "_hash", guarded_hash)
    result = local_tools.run_tool("duplicate_detector", {"path": str(tmp_path)})
    assert result["status"] == "OK"
    assert result["duplicate_files"] == 0


def test_agent_reconnects_until_server_recovers(monkeypatch):
    attempts = {"count": 0}

    class FakeAPI:
        def __init__(self, _url): pass
        def poll(self, *_args):
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise ConnectionError("offline")
            raise KeyboardInterrupt

    monkeypatch.setattr(cli, "is_configured", lambda: True)
    monkeypatch.setattr(cli, "load_config", lambda: {"server_url": "http://test", "email": "u@test", "device_id": 1, "device_key": "key"})
    monkeypatch.setattr(cli, "AgentAPI", FakeAPI)
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)
    assert cli.cmd_run(argparse.Namespace()) == 0
    assert attempts["count"] == 3


def test_autostart_can_be_enabled_and_disabled(tmp_path, monkeypatch):
    target = tmp_path / "com.beresin.agent.plist"
    monkeypatch.setattr(cli, "_autostart_paths", lambda: [target])
    monkeypatch.setattr(cli, "_launch_agent_plist", lambda: target)
    monkeypatch.setattr(cli.sys, "platform", "darwin")
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: None)
    target.write_text("plist")
    cli._disable_autostart()
    assert not target.exists()


def test_upgrade_accepts_only_local_agent_wheel(tmp_path, monkeypatch):
    wheel = tmp_path / "beresin_agent-2.0.0-py3-none-any.whl"
    wheel.write_bytes(b"wheel")
    calls = []
    monkeypatch.setattr(cli.shutil, "which", lambda command: "/usr/bin/uv" if command == "uv" else None)
    monkeypatch.setattr(cli.subprocess, "run", lambda command, check=False: calls.append(command) or type("Result", (), {"returncode": 0})())
    assert cli.cmd_upgrade(argparse.Namespace(wheel=str(wheel))) == 0
    assert calls[0] == [
        "/usr/bin/uv", "pip", "install", "--python", cli.sys.executable,
        "--upgrade", "--no-deps", str(wheel),
    ]
    invalid = tmp_path / "other.whl"
    invalid.write_bytes(b"wheel")
    assert cli.cmd_upgrade(argparse.Namespace(wheel=str(invalid))) == 2


def test_upgrade_falls_back_to_pip_when_uv_is_unavailable(tmp_path, monkeypatch):
    wheel = tmp_path / "beresin_agent-2.0.0-py3-none-any.whl"
    wheel.write_bytes(b"wheel")
    calls = []
    monkeypatch.setattr(cli.shutil, "which", lambda _command: None)
    monkeypatch.setattr(cli.subprocess, "run", lambda command, check=False: calls.append(command) or type("Result", (), {"returncode": 0})())
    assert cli.cmd_upgrade(argparse.Namespace(wheel=str(wheel))) == 0
    assert calls[0][:4] == [cli.sys.executable, "-m", "pip", "install"]


def test_uninstall_disables_autostart_and_clears_local_state(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_disable_autostart", lambda: calls.append("autostart"))
    monkeypatch.setattr(cli, "clear_config", lambda: calls.append("config"))
    assert cli.cmd_uninstall(argparse.Namespace(keep_config=False)) == 0
    assert calls == ["autostart", "config"]


def test_startup_probe_requires_real_boot_change(monkeypatch):
    state = {}
    monkeypatch.setattr(cli, "set_state", lambda key, value: state.__setitem__(key, value))
    monkeypatch.setattr(cli, "get_state", lambda key, default=None: state.get(key, default))
    monkeypatch.setattr(cli, "_boot_identifier", lambda: "boot-a")
    assert cli.cmd_startup_probe(argparse.Namespace(action="record")) == 0
    assert cli.cmd_startup_probe(argparse.Namespace(action="verify")) == 3
    monkeypatch.setattr(cli, "_boot_identifier", lambda: "boot-b")
    monkeypatch.setattr(cli, "_autostart_enabled", lambda: False)
    assert cli.cmd_startup_probe(argparse.Namespace(action="verify")) == 4


def test_frozen_binary_autostart_command_does_not_use_python_module_flag(monkeypatch):
    monkeypatch.setattr(cli.sys, "frozen", True, raising=False)
    monkeypatch.setattr(cli.sys, "executable", "/Applications/BERESIN Agent")
    assert cli._agent_run_command() == ["/Applications/BERESIN Agent", "run"]
    monkeypatch.delattr(cli.sys, "frozen", raising=False)
    assert cli._agent_run_command()[-3:] == ["-m", "beresin_agent.cli", "run"]


def test_config_file_permissions_and_no_plaintext_secrets(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(config, "_store_secret", lambda field, value: "enc:" + field)
    config.save_config("https://server", 1, "device-secret", "u@test", "token-secret")
    raw = config.CONFIG_FILE.read_text()
    assert "device-secret" not in raw
    assert "token-secret" not in raw
    # POSIX permission bits are not meaningful on Windows. Secrets are still
    # absent from the file there and stored through the OS credential vault.
    if os.name != "nt":
        assert config.CONFIG_FILE.stat().st_mode & 0o777 == 0o600


def test_index_is_incremental_versioned_and_removes_stale_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / ".beresin")
    workspace = tmp_path / "files"
    workspace.mkdir()
    monkeypatch.setattr(config, "workspace_root", lambda: workspace)
    first = workspace / "a.txt"
    second = workspace / "b.txt"
    first.write_text("alpha")
    second.write_text("beta")
    initial = local_tools.run_tool("semantic_indexer", {"path": str(workspace)})
    assert initial["indexed"] == 2
    repeated = local_tools.run_tool("semantic_indexer", {"path": str(workspace)})
    assert repeated["indexed"] == 0
    assert repeated["unchanged"] == 2
    first.unlink()
    second.write_text("beta changed")
    refreshed = local_tools.run_tool("semantic_indexer", {"path": str(workspace)})
    assert refreshed["indexed"] == 1
    assert refreshed["stale_removed"] == 1
    manifest = json.loads((config.CONFIG_DIR / "index.json").read_text())
    assert manifest["schema_version"] == 2
    assert [item["name"] for item in manifest["items"]] == ["b.txt"]


def test_recommendation_snapshot_rejects_changed_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "workspace_root", lambda: tmp_path)
    for index in range(5):
        (tmp_path / f"doc-{index}.pdf").write_bytes(b"original")
    result = local_tools.run_tool("folder_organizer", {"path": str(tmp_path)})
    recommendation = next(item for item in result["recommendations"] if item["id"] == "by-type")
    changed = tmp_path / "doc-0.pdf"
    changed.write_bytes(b"changed after review")
    execution = local_tools.run_tool("batch_executor", recommendation["apply"]["tool_args"])
    assert execution["status"] == "PARTIAL"
    assert changed.exists()
    assert any("berubah sejak review" in error for error in execution["errors"])


def test_mutation_refuses_destination_collision(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "workspace_root", lambda: tmp_path)
    source_dir = tmp_path / "source"
    destination = tmp_path / "destination"
    source_dir.mkdir()
    destination.mkdir()
    source = source_dir / "same.txt"
    source.write_text("new")
    (destination / "same.txt").write_text("existing")
    result = local_tools.run_tool("file_move", {"path": str(source), "destination": str(destination)})
    assert result["status"] == "ERROR"
    assert source.exists()
    assert (destination / "same.txt").read_text() == "existing"


def test_mutation_refuses_symlink_escape(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    target = outside / "secret.txt"
    target.write_text("secret")
    link = workspace / "link.txt"
    link.symlink_to(target)
    monkeypatch.setattr(config, "workspace_root", lambda: workspace)
    result = local_tools.run_tool("file_delete", {"path": str(link)})
    assert result["status"] == "ERROR"
    assert any("di luar workspace" in error for error in result["errors"])
    assert target.exists()


def test_scan_supports_multiple_allowed_roots(tmp_path, monkeypatch):
    first = tmp_path / "Downloads"
    second = tmp_path / "Documents"
    first.mkdir()
    second.mkdir()
    (second / "laporan.txt").write_text("ok")
    monkeypatch.setattr(config, "allowed_roots", lambda: [first, second])

    result = local_tools.run_tool("filesystem_scanner", {"path": str(second)})

    assert result["status"] == "OK"
    assert result["file_count"] == 1


def test_scan_rejects_outside_multi_root_and_sensitive_paths(tmp_path, monkeypatch):
    allowed = tmp_path / "Documents"
    outside = tmp_path / "Outside"
    allowed.mkdir()
    outside.mkdir()
    monkeypatch.setattr(config, "allowed_roots", lambda: [allowed])
    with pytest.raises(PermissionError, match="di luar workspace"):
        local_tools.run_tool("filesystem_scanner", {"path": str(outside)})

    home = Path.home()
    monkeypatch.setattr(config, "allowed_roots", lambda: [home])
    with pytest.raises(PermissionError, match="sensitif"):
        local_tools.run_tool("filesystem_scanner", {"path": str(home / ".ssh")})


def test_copy_verification_uses_hash_not_only_size(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "workspace_root", lambda: tmp_path)
    source = tmp_path / "source.txt"
    destination = tmp_path / "copies"
    source.write_bytes(b"AAAA")
    destination.mkdir()

    def corrupt_copy(_source, target):
        Path(target).write_bytes(b"BBBB")

    monkeypatch.setattr(local_tools.shutil, "copy2", corrupt_copy)
    result = local_tools.run_tool("file_copy", {"path": str(source), "destination": str(destination)})
    assert result["status"] == "PARTIAL"
    assert result["verified_count"] == 0


def test_corrupt_unsupported_and_large_files_fail_softly(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "workspace_root", lambda: tmp_path)
    corrupt = tmp_path / "corrupt.pdf"
    corrupt.write_bytes(b"not a valid PDF")
    unsupported = tmp_path / "unknown.bin"
    unsupported.write_bytes(b"\x00\x01")
    large = tmp_path / "large.dat"
    with large.open("wb") as handle:
        handle.truncate(12 * 1024 * 1024)
    assert local_tools.run_tool("document_parser", {"path": str(corrupt)})["status"] == "OK"
    assert local_tools.run_tool("document_parser", {"path": str(unsupported)})["status"] == "OK"
    scan = local_tools.run_tool("filesystem_scanner", {"path": str(tmp_path)})
    assert scan["status"] == "OK"
    assert scan["file_count"] == 3


def test_read_tools_refuse_paths_outside_workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("secret")
    monkeypatch.setattr(config, "workspace_root", lambda: workspace)
    for tool, arguments in (
        ("filesystem_scanner", {"path": str(outside)}),
        ("file_search", {"directory": str(outside), "query": "secret"}),
        ("document_parser", {"path": str(outside / "secret.txt")}),
        ("semantic_indexer", {"path": str(outside)}),
    ):
        with pytest.raises(PermissionError, match="di luar workspace"):
            local_tools.run_tool(tool, arguments)


def test_batch_moves_multiple_files_into_same_new_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "workspace_root", lambda: tmp_path)
    first = tmp_path / "laporan-2025.txt"
    second = tmp_path / "laporan-2025-copy.txt"
    first.write_text("sama", encoding="utf-8")
    second.write_text("sama", encoding="utf-8")
    destination = tmp_path / "2025"
    result = local_tools.run_tool("batch_executor", {
        "operation": "move",
        "moves": [
            {"source": str(first), "destination": str(destination)},
            {"source": str(second), "destination": str(destination)},
        ],
    })
    assert result["status"] == "OK"
    assert result["verified_count"] == 2
    assert (destination / first.name).is_file()
    assert (destination / second.name).is_file()
    assert not (destination / second.name).is_dir()
