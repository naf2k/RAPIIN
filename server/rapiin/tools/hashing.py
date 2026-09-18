"""File hashing shared by duplicate detection and verification."""
from __future__ import annotations

import hashlib
from pathlib import Path


def file_hash(path: Path, chunk_size: int = 65536) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
