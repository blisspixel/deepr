#!/usr/bin/env python3
"""Read one version section from the changelog for GitHub release notes.

The release workflow attaches these notes when it creates the release. A missing
section falls back to a short summary so publication of the built assets still
proceeds.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_HEADING = re.compile(r"^## \[([^\]]+)\]")


def fallback_summary(version: str) -> str:
    """Return the short summary used when a changelog section is missing."""
    normalized = version.removeprefix("v")
    return f"Deepr {normalized}. See docs/CHANGELOG.md.\n"


def changelog_section(changelog: str, version: str) -> str | None:
    """Return the changelog section for ``version``, including its heading."""
    normalized = version.removeprefix("v")
    lines = changelog.splitlines()
    start: int | None = None
    for index, line in enumerate(lines):
        match = _HEADING.match(line)
        if match and match.group(1) == normalized:
            start = index
            break
    if start is None:
        return None
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if _HEADING.match(lines[index]):
            end = index
            break
    section = "\n".join(lines[start:end]).strip()
    if not section:
        return None
    return section + "\n"


def release_notes_text(changelog: str, version: str) -> str:
    """Return the version section, or a short summary when it is absent."""
    section = changelog_section(changelog, version)
    if section is None:
        return fallback_summary(version)
    return section


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print("usage: release_notes.py VERSION CHANGELOG", file=sys.stderr)
        return 2
    version, path_text = args
    path = Path(path_text)
    if not path.is_file():
        print(f"Changelog not found: {path}", file=sys.stderr)
        sys.stdout.write(fallback_summary(version))
        return 0
    changelog = path.read_text(encoding="utf-8")
    notes = release_notes_text(changelog, version)
    if notes == fallback_summary(version):
        normalized = version.removeprefix("v")
        print(f"No changelog section for {normalized}; using a short summary.", file=sys.stderr)
    sys.stdout.write(notes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
