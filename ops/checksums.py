#!/usr/bin/env python3
"""Write deterministic SHA-256 checksums for release artifacts."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, default=Path("SHA256SUMS"))
    args = parser.parse_args()
    files = sorted(path for path in args.directory.iterdir() if path.is_file() and path.resolve() != args.output.resolve())
    args.output.write_text("".join(f"{digest(path)}  {path.name}\n" for path in files), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
