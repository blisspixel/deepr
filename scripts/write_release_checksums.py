#!/usr/bin/env python3
"""Write SHA256SUMS for files in a release directory.

The GitHub release checksum file uses GNU sha256sum form: a lowercase hex
digest, two spaces, and the file name. The checksum file itself is not hashed.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

CHECKSUM_NAME = "SHA256SUMS"


def checksum_lines(directory: Path) -> list[str]:
    """Return sorted checksum lines for every file except SHA256SUMS."""
    files = sorted(path for path in directory.iterdir() if path.is_file() and path.name != CHECKSUM_NAME)
    lines: list[str] = []
    for path in files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.name}")
    return lines


def write_checksums(directory: Path) -> Path:
    """Write SHA256SUMS in ``directory`` and return its path."""
    lines = checksum_lines(directory)
    if not lines:
        raise ValueError(f"No release files to checksum in {directory}")
    target = directory / CHECKSUM_NAME
    target.write_text("\n".join(lines) + "\n", encoding="ascii", newline="\n")
    return target


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: write_release_checksums.py DIRECTORY", file=sys.stderr)
        return 2
    directory = Path(args[0])
    if not directory.is_dir():
        print(f"Not a directory: {directory}", file=sys.stderr)
        return 2
    try:
        write_checksums(directory)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
