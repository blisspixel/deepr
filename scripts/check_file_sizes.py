#!/usr/bin/env python3
"""File-size ratchet (Phase Q0.1).

Fails if any deepr/*.py file exceeds the line CEILING, unless it is an
explicitly grandfathered file - and even then, a grandfathered file may not
grow past the size recorded here. The goal is twofold:

1. No *new* oversized file can ever be introduced.
2. The existing large files (the Phase Q3 decomposition backlog) can only
   shrink; the allowlist is a debt register that ratchets down, never up.

Run: python scripts/check_file_sizes.py
Design rationale: docs/design/code-health.md
"""

from __future__ import annotations

import sys
from pathlib import Path

CEILING = 1000

# Files allowed over CEILING, each capped at its line count on 2026-06-12.
# This dict only ever shrinks: when Phase Q3 splits a file below CEILING,
# remove its entry; if a file shrinks but stays over CEILING, lower its cap.
GRANDFATHERED: dict[str, int] = {
    "deepr/web/app.py": 3992,
    "deepr/cli/commands/semantic/experts.py": 3338,
    "deepr/experts/chat.py": 2633,
    "deepr/experts/lazy_graph_rag.py": 2036,
    "deepr/mcp/server.py": 1937,
    "deepr/experts/beliefs.py": 1406,
    "deepr/cli/commands/run.py": 1363,
    "deepr/experts/curriculum.py": 1340,
    "deepr/experts/memory.py": 1287,
    "deepr/experts/learner.py": 1287,
    "deepr/providers/registry.py": 1279,
    "deepr/observability/costs.py": 1146,
    "deepr/core/settings.py": 1120,
    "deepr/cli/commands/prep.py": 1094,
    "deepr/cli/commands/research.py": 1049,
    "deepr/api/app.py": 1028,
    "deepr/cli/commands/semantic/artifacts.py": 1012,
}

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _line_count(path: Path) -> int:
    """Newline count, matching `wc -l` (the source of the baselines)."""
    return path.read_text(encoding="utf-8", errors="replace").count("\n")


def main() -> int:
    pkg = _REPO_ROOT / "deepr"
    failures: list[str] = []
    nudges: list[str] = []

    seen_grandfathered: set[str] = set()

    for path in sorted(pkg.rglob("*.py")):
        rel = path.relative_to(_REPO_ROOT).as_posix()
        lines = _line_count(path)
        cap = GRANDFATHERED.get(rel)

        if cap is not None:
            seen_grandfathered.add(rel)
            if lines > cap:
                failures.append(f"  {rel}: {lines} lines exceeds its grandfathered cap of {cap} (it must not grow)")
            elif lines <= CEILING:
                nudges.append(f"  {rel}: now {lines} lines (<= {CEILING}) - remove it from GRANDFATHERED")
            continue

        if lines > CEILING:
            failures.append(f"  {rel}: {lines} lines exceeds the {CEILING}-line ceiling (split it or it is debt)")

    # A grandfathered entry that no longer matches a file (renamed/deleted)
    # should be cleaned up so the register stays honest.
    stale = sorted(set(GRANDFATHERED) - seen_grandfathered)
    for rel in stale:
        nudges.append(f"  {rel}: in GRANDFATHERED but not found - remove the stale entry")

    if nudges:
        print("File-size ratchet - allowlist can be tightened:")
        print("\n".join(nudges))
        print()

    if failures:
        print("File-size ratchet FAILED:")
        print("\n".join(failures))
        print(f"\nCeiling is {CEILING} lines. See docs/design/code-health.md (Phase Q).")
        return 1

    print(f"File-size ratchet OK: no file over {CEILING} lines except {len(GRANDFATHERED)} grandfathered (none grew).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
