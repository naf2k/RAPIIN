"""Workspace grounding tests.

The server must anchor every tool path to a device root without inventing a
path that could touch the wrong file (workspace-isolation rules).
"""
import os

from rapiin.workspace import ground_arguments, validate_arguments


def _roots(tmp_path):
    root = tmp_path / "Downloads"
    root.mkdir()
    return [str(root)], root


def test_bare_filename_with_folder_path_stays_in_folder(tmp_path):
    """`path` naming a folder must anchor bare `paths` entries inside it.

    Regression: only source/directory were treated as the base folder, so a
    folder sent in `path` plus a bare filename in `paths` was anchored to the
    workspace root — potentially acting on a same-named file at the root.
    """
    roots, root = _roots(tmp_path)
    sub = root / "_APPR"
    sub.mkdir()
    (sub / "approve-aku.txt").write_text("isi")

    grounded = ground_arguments(
        {"path": str(sub), "paths": ["approve-aku.txt"]},
        roots,
    )
    assert grounded["paths"] == [os.path.join(str(sub), "approve-aku.txt")]


def test_absolute_path_list_is_never_rewritten(tmp_path):
    roots, root = _roots(tmp_path)
    sub = root / "_APPR"
    sub.mkdir()
    target = str(sub / "a.txt")
    grounded = ground_arguments({"path": str(sub), "paths": [target]}, roots)
    assert grounded["paths"] == [target]


def test_source_folder_still_anchors_bare_names(tmp_path):
    roots, root = _roots(tmp_path)
    sub = root / "lama"
    sub.mkdir()
    grounded = ground_arguments({"source": str(sub), "paths": ["x.txt"]}, roots)
    assert grounded["paths"] == [os.path.join(str(sub), "x.txt")]


def test_relative_path_without_folder_anchors_to_first_root(tmp_path):
    roots, root = _roots(tmp_path)
    grounded = ground_arguments({"path": "notes.txt"}, roots)
    assert grounded["path"] == os.path.join(str(root), "notes.txt")


def test_path_outside_roots_is_rejected(tmp_path):
    roots, _ = _roots(tmp_path)
    grounded = ground_arguments({"path": "/etc/passwd"}, roots)
    assert validate_arguments(grounded, roots) is not None


def test_stale_path_naming_a_root_basename_resolves_to_that_root(tmp_path):
    roots, root = _roots(tmp_path)
    grounded = ground_arguments({"path": "/opt/Downloads"}, roots)
    assert grounded["path"] == str(root)
