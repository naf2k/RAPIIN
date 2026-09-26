"""Tes pemeriksa aset rilis (ops/check_release_assets.py).

Fokus pada fungsi murni tanpa jaringan, supaya logika konvensi nama aset —
yang menentukan berhasil/gagalnya pemasangan karyawan — selalu terjaga.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "ops" / "check_release_assets.py"

spec = importlib.util.spec_from_file_location("check_release_assets", CHECKER)
assert spec and spec.loader
checker = importlib.util.module_from_spec(spec)
sys.modules["check_release_assets"] = checker
spec.loader.exec_module(checker)


def _release(tag: str, names: list[str], *, draft: bool = False, sums_url: str = "") -> dict:
    return {
        "tag_name": tag,
        "draft": draft,
        "assets": [
            {"name": name, "browser_download_url": sums_url if name == "SHA256SUMS" else "https://example.invalid/x"}
            for name in names
        ],
    }


def test_expected_assets_follow_installer_convention():
    assert checker.expected_assets("1.1.1") == {
        "rapiin_agent-1.1.1-py3-none-any.whl",
        "rapiin_agent-1.1.1.tar.gz",
        "SHA256SUMS",
    }


def test_healthy_release_has_no_problems():
    release = _release(
        "rapiin-v1.1.1",
        ["rapiin_agent-1.1.1-py3-none-any.whl", "rapiin_agent-1.1.1.tar.gz", "SHA256SUMS"],
        sums_url="not-a-url",  # memaksa jalur "URL tidak valid" tanpa jaringan
    )
    problems = checker.check_release("naf2k/RAPIIN", release)
    # Satu-satunya masalah yang boleh muncul adalah URL checksum sintetis.
    assert all("tidak valid" in p for p in problems), problems


def test_old_tag_convention_is_rejected():
    """Tag `agent-v1.0.0` pernah ada dan memakai nama paket lama."""
    problems = checker.check_release("naf2k/RAPIIN", _release("agent-v1.0.0", ["beresin_agent-1.0.0-py3-none-any.whl"]))
    assert problems and "tidak mengikuti pola" in problems[0]


def test_missing_assets_are_reported():
    problems = checker.check_release("naf2k/RAPIIN", _release("rapiin-v9.9.9", ["SHA256SUMS"]))
    joined = " ".join(problems)
    assert "rapiin_agent-9.9.9-py3-none-any.whl" in joined
    assert "rapiin_agent-9.9.9.tar.gz" in joined


def test_draft_release_is_reported():
    release = _release(
        "rapiin-v1.1.1",
        ["rapiin_agent-1.1.1-py3-none-any.whl", "rapiin_agent-1.1.1.tar.gz", "SHA256SUMS"],
        draft=True,
        sums_url="not-a-url",
    )
    assert any("draft" in p for p in checker.check_release("naf2k/RAPIIN", release))
