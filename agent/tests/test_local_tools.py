"""Tests for the Desktop Agent local tools (agent package)."""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from beresin_agent import local_tools
from beresin_agent import config


def _set_workspace(tmp: str):
    config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config.CONFIG_FILE.write_text(json.dumps({"workspace": tmp}), encoding="utf-8")


def test_local_scan():
    with tempfile.TemporaryDirectory() as d:
        _set_workspace(d)
        Path(d, "a.txt").write_text("hello")
        Path(d, "b.md").write_text("world")
        result = local_tools.run_tool("filesystem_scanner", {"path": d})
        assert result["status"] == "OK"
        assert result["file_count"] == 2


def test_local_search():
    with tempfile.TemporaryDirectory() as d:
        _set_workspace(d)
        Path(d, "laporan.pdf").write_text("x")
        Path(d, "foto.png").write_bytes(b"png")
        result = local_tools.run_tool("file_search", {"directory": d, "extension": "pdf"})
        assert result["count"] == 1
        assert result["results"][0]["name"] == "laporan.pdf"


def test_local_duplicates():
    with tempfile.TemporaryDirectory() as d:
        _set_workspace(d)
        Path(d, "a.txt").write_text("sama")
        Path(d, "b.txt").write_text("sama")
        result = local_tools.run_tool("duplicate_detector", {"path": d})
        assert result["duplicate_groups"] == 1
        assert result["duplicate_files"] == 1


def test_scan_and_duplicates_ignore_hidden_files_and_app_bundles():
    with tempfile.TemporaryDirectory() as d:
        _set_workspace(d)
        Path(d, "visible-a.txt").write_text("same")
        Path(d, "visible-b.txt").write_text("same")
        Path(d, ".hidden.txt").write_text("same")
        bundle = Path(d, "Photos Library.photoslibrary", "originals")
        bundle.mkdir(parents=True)
        Path(bundle, "managed-a.jpg").write_text("managed")
        Path(bundle, "managed-b.jpg").write_text("managed")
        photo_booth = Path(d, "Photo Booth Library", "Originals")
        photo_booth.mkdir(parents=True)
        Path(photo_booth, "managed-c.jpg").write_text("managed")
        Path(photo_booth, "managed-d.jpg").write_text("managed")

        scan = local_tools.run_tool("filesystem_scanner", {"path": d})
        assert scan["file_count"] == 2
        duplicates = local_tools.run_tool("duplicate_detector", {"path": d})
        assert duplicates["duplicate_groups"] == 1
        assert duplicates["duplicate_files"] == 1
        duplicates = local_tools.run_tool("duplicate_detector", {"path": d})

        assert scan["file_count"] == 2
        assert duplicates["duplicate_groups"] == 1
        assert duplicates["duplicate_files"] == 1
        assert all("photoslibrary" not in path.lower() for group in duplicates["groups"] for path in group["duplicates"])


def test_local_classifier():
    with tempfile.TemporaryDirectory() as d:
        _set_workspace(d)
        Path(d, "gambar.png").write_bytes(b"png")
        Path(d, "data.xlsx").write_bytes(b"xlsx")
        result = local_tools.run_tool("file_classifier", {"path": d})
        cats = {c["category"] for c in result["categories"]}
        assert "images" in cats
        assert "spreadsheets" in cats


def test_local_move_and_verify():
    with tempfile.TemporaryDirectory() as ws:
        _set_workspace(ws)
        Path(ws, "a.txt").write_text("hello")
        dest = Path(ws, "sub")
        dest.mkdir()
        result = local_tools.run_tool("file_move", {"source": str(Path(ws, "a.txt")), "destination": str(dest)})
        assert result["status"] == "OK"
        assert result["verified_count"] == 1
        assert (dest / "a.txt").exists()
        assert not (Path(ws) / "a.txt").exists()


def test_local_delete_with_guard():
    with tempfile.TemporaryDirectory() as ws:
        _set_workspace(ws)
        Path(ws, "hapus.txt").write_text("x")
        result = local_tools.run_tool("file_delete", {"path": str(Path(ws, "hapus.txt"))})
        assert result["status"] == "OK"
        assert result["verified_count"] == 1
        assert not (Path(ws) / "hapus.txt").exists()

        # Outside the workspace -> refused (ERROR, nothing executed).
        outside = Path(tempfile.mkdtemp()) / "b.txt"
        outside.write_text("x")
        result = local_tools.run_tool("file_delete", {"path": str(outside)})
        assert result["status"] == "ERROR"
        assert outside.exists()
        shutil.rmtree(outside.parent, ignore_errors=True)


def test_local_batch_copy():
    with tempfile.TemporaryDirectory() as ws:
        _set_workspace(ws)
        for i in range(3):
            Path(ws, f"f{i}.txt").write_text(f"isi {i}")
        dest = Path(ws, "arsip")
        dest.mkdir()
        files = [str(Path(ws, f"f{i}.txt")) for i in range(3)]
        result = local_tools.run_tool(
            "batch_executor",
            {"operation": "copy", "paths": files, "destination": str(dest)},
        )
        assert result["status"] == "OK"
        assert result["verified_count"] == 3


def test_copy_resolves_relative_paths_against_source_directory():
    with tempfile.TemporaryDirectory() as ws:
        _set_workspace(ws)
        source_dir = Path(ws, "Dokumen")
        source_dir.mkdir()
        source = source_dir / "catatan.txt"
        source.write_text("isi")
        result = local_tools.run_tool("file_copy", {
            "source": str(source_dir),
            "paths": ["catatan.txt"],
            "destination": ws,
        })
        assert result["status"] == "OK"
        assert result["verified_count"] == 1
        assert source.is_file()
        assert Path(ws, "catatan.txt").read_text() == "isi"


def test_unknown_tool():
    result = local_tools.run_tool("file_foobar", {"path": "/x"})
    assert result["status"] == "ERROR"
