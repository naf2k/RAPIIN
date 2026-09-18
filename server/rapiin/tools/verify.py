"""Verification - confirm that executed operations really happened.

Used by the agent pipeline (PRD section 29): after a move/copy/delete the
result is checked against the filesystem before the task is marked verified.
"""
from __future__ import annotations

from pathlib import Path

from .hashing import file_hash


def verify_move(source: str, destination: str) -> dict:
    src = Path(source)
    dst = Path(destination)
    if src.exists():
        return {"verified": False, "reason": "Sumber masih ada; pemindahan tidak lengkap."}
    if not dst.exists():
        return {"verified": False, "reason": "File tujuan tidak ditemukan."}
    return {"verified": True, "destination": str(dst)}


def verify_copy(source: str, destination: str) -> dict:
    src = Path(source)
    dst = Path(destination)
    if not src.exists() or not dst.exists():
        return {"verified": False, "reason": "Sumber atau salinan tidak ditemukan."}
    try:
        if file_hash(src) != file_hash(dst):
            return {"verified": False, "reason": "Hash sumber dan salinan berbeda."}
    except OSError:
        return {"verified": False, "reason": "Sumber atau salinan tidak dapat dibaca."}
    return {"verified": True, "destination": str(dst), "hash": "match"}


def verify_delete(path: str) -> dict:
    if Path(path).exists():
        return {"verified": False, "reason": "File masih ada."}
    return {"verified": True, "path": path}


def verify_hash(source: str, destination: str) -> dict:
    try:
        if file_hash(Path(source)) == file_hash(Path(destination)):
            return {"verified": True, "hash": "match"}
    except OSError:
        pass
    return {"verified": False, "reason": "Hash tidak cocok atau file tidak dapat dibaca."}
