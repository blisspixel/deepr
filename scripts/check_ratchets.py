#!/usr/bin/env python3
"""Complexity and security ratchets (Phase Q0.2 / Q0.3).

Counts the advisory ruff findings that are not yet blocking - cyclomatic
complexity (C901) and security (S/bandit) - and fails CI if either count
*grows* past its committed baseline. This stops the backlog from getting
worse while Phase Q4 pays it down; each baseline only ever ratchets down.

Pinned to one ruff version (see pyproject [dev] and .github/workflows/ci.yml)
so counts are reproducible between local runs and CI.

Run: python scripts/check_ratchets.py
Design rationale: docs/design/code-health.md
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Baselines measured 2026-06-12 with ruff 0.15.17 over deepr/. These are
# ceilings: the count may fall (then lower the baseline) but never rise.
BASELINES: dict[str, int] = {
    "C901": 146,  # functions over the mccabe complexity cap (max-complexity 10)
    "S": 97,  # flake8-bandit security findings
}


def _ruff_cmd() -> list[str]:
    exe = shutil.which("ruff")
    if exe:
        return [exe]
    return [sys.executable, "-m", "ruff"]


def _count(rule: str) -> int:
    """Number of ruff findings for a single selected rule group over deepr/."""
    proc = subprocess.run(
        [*_ruff_cmd(), "check", "deepr/", "--select", rule, "--output-format", "json"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    out = proc.stdout.strip()
    if not out:
        # ruff exits non-zero when findings exist; empty stdout means a real
        # invocation error (surface it rather than silently reporting 0).
        raise RuntimeError(f"ruff produced no JSON for --select {rule}:\n{proc.stderr.strip()}")
    return len(json.loads(out))


def main() -> int:
    failures: list[str] = []
    nudges: list[str] = []

    for rule, baseline in BASELINES.items():
        count = _count(rule)
        if count > baseline:
            failures.append(
                f"  {rule}: {count} findings exceeds the baseline of {baseline} "
                f"(+{count - baseline}). New {rule} debt is not allowed - fix it or refactor."
            )
        elif count < baseline:
            nudges.append(
                f"  {rule}: down to {count} (baseline {baseline}) - lower the baseline in scripts/check_ratchets.py"
            )
        else:
            print(f"{rule} ratchet OK: {count} findings (at baseline).")

    if nudges:
        print("\nRatchets improved - tighten the baselines:")
        print("\n".join(nudges))

    if failures:
        print("\nCode-health ratchet FAILED:")
        print("\n".join(failures))
        print("\nSee docs/design/code-health.md (Phase Q).")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
