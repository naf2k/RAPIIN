"""Tests for reversible trash (FULL_AUTO deletes must be undoable)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rapiin_agent import config, local_tools, trash


def _set_workspace(tmp: str):
    config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config.CONFIG_FILE.write_text(json.dumps({"workspace": tmp}), encoding="utf-8")


def test_delete_without_reversible_flag_still_unlinks():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        _set_workspace(d)
        target = Path(d, "hapus.txt")
        target.write_text("isi")
        result = local_tools.run_tool("file_delete", {"paths": [str(target)]})
        assert result["status"] == "OK"
        assert not target.exists()


def test_reversible_delete_moves_to_trash_and_reports_id():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        _set_workspace(d)
        target = Path(d, "penting.txt")
        target.write_text("jangan hilang")
        result = local_tools.run_tool("file_delete", {"paths": [str(target)], "reversible": True})

        assert result["status"] == "OK"
        assert result["reversible"] is True
        assert result["trash_id"]
        assert not target.exists()
        assert Path(result["trash_dir"]).is_dir()
        # The manifest records the original location.
        manifest = json.loads((Path(result["trash_dir"]) / "manifest.json").read_text())
        assert manifest["items"][0]["original"] == str(target)


def test_restore_puts_file_back():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        _set_workspace(d)
        target = Path(d, "restoreme.txt")
        target.write_text("isi asli")
        deleted = local_tools.run_tool("file_delete", {"paths": [str(target)], "reversible": True})
        trash_id = deleted["trash_id"]

        restored = local_tools.run_tool("file_restore", {"trash_id": trash_id})
        assert restored["status"] == "OK"
        assert restored["restored_count"] == 1
        assert target.exists()
        assert target.read_text() == "isi asli"


def test_trash_list_shows_batch():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        _set_workspace(d)
        target = Path(d, "listed.txt")
        target.write_text("x")
        deleted = local_tools.run_tool("file_delete", {"paths": [str(target)], "reversible": True})

        listed = local_tools.run_tool("trash_list", {})
        assert listed["status"] == "OK"
        assert listed["count"] == 1
        assert listed["entries"][0]["id"] == deleted["trash_id"]


def test_restore_does_not_overwrite_existing_file():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        _set_workspace(d)
        target = Path(d, "dup.txt")
        target.write_text("versi lama")
        deleted = local_tools.run_tool("file_delete", {"paths": [str(target)], "reversible": True})
        # A new file appears at the original location before undo.
        target.write_text("versi baru")

        restored = local_tools.run_tool("file_restore", {"trash_id": deleted["trash_id"]})
        assert restored["skipped_count"] == 1
        assert target.read_text() == "versi baru"


def test_restore_unknown_id_errors():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        _set_workspace(d)
        result = trash.restore_trash("tidak-ada")
        assert result["status"] == "ERROR"


def test_trash_requires_path():
    result = trash.trash_paths([])
    assert result["status"] == "ERROR"
