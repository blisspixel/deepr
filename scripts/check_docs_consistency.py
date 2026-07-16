#!/usr/bin/env python3
"""Guard against documentation drift for volatile project facts.

Some facts (test count, MCP tool count, coverage gate) are easy to restate in
prose and then forget to update. This script derives each fact from its real
source of truth in the code and checks that the small allowlist of docs that
quote it stays correct. It is intentionally narrow: it only scans the
(file, pattern) pairs listed in CHECKS, so it never has to understand arbitrary
prose. When a doc is reworded so a pattern no longer matches, that is treated as
a failure too, which keeps the allowlist honest.

Canonical homes (see docs/README.md "Source of truth" table):
  - test count, coverage gate -> ROADMAP.md "Current Status"
  - MCP tool count            -> mcp/README.md (full tool tables + footer)
  - model names / pricing      -> src/deepr/providers/registry.py (checked elsewhere)

Run from anywhere:  python scripts/check_docs_consistency.py
Exit code 0 = all consistent, 1 = at least one drift detected.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# Facts derived from source of truth
# --------------------------------------------------------------------------- #


def count_test_functions() -> int:
    """Number of `def test_*` functions across the suite.

    This is a conservative proxy for the collected test count: pytest collects
    at least one case per test function (parametrize only adds more), so the
    real collected count is >= this number. That makes it safe to use for a
    "floor" check (docs say "N+ tests"): a doc only fails if it claims MORE than
    the functions that actually exist.
    """
    tests_dir = REPO_ROOT / "tests"
    pattern = re.compile(r"\bdef test_\w*\s*\(")
    total = 0
    for path in tests_dir.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        total += len(pattern.findall(path.read_text(encoding="utf-8", errors="ignore")))
    return total


def coverage_gate() -> int:
    """The enforced coverage threshold from pyproject.toml (fail_under)."""
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r"fail_under\s*=\s*(\d+)", text)
    if not match:
        raise RuntimeError("could not find fail_under in pyproject.toml")
    return int(match.group(1))


def mcp_tool_count() -> int:
    """Number of registered MCP tools (dispatch keys across server and adapters)."""
    keys: set[str] = set()
    # Conversation tools live in expert_conversation.conversation_tool_dispatch
    # and are merged into server tool_dispatch via **spread, so count both files.
    for rel in (
        "src/deepr/mcp/server.py",
        "src/deepr/mcp/expert_conversation.py",
    ):
        path = REPO_ROOT / rel
        if path.is_file():
            keys.update(re.findall(r'"(deepr_\w+)":\s*lambda', path.read_text(encoding="utf-8")))
    if not keys:
        raise RuntimeError("could not find tool_dispatch entries in MCP sources")
    return len(keys)


def builtin_skill_count() -> int:
    """Number of built-in expert skills (src/deepr/skills/*/skill.yaml)."""
    skills_dir = REPO_ROOT / "src" / "deepr" / "skills"
    return sum(1 for _ in skills_dir.glob("*/skill.yaml"))


FACTS = {
    "tests": count_test_functions,
    "coverage": coverage_gate,
    "mcp_tools": mcp_tool_count,
    "skills": builtin_skill_count,
}


# --------------------------------------------------------------------------- #
# Allowlist: the only places a fact may be quoted
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Check:
    path: str  # repo-relative
    pattern: str  # one capture group = the quoted number
    fact: str  # key into FACTS
    mode: str  # "exact" or "floor"


CHECKS: list[Check] = [
    # Front-door README (kept current via this check, not by discipline)
    Check("README.md", r"(\d[\d,]*)\+ tests \(Python 3\.12[-/0-9.]*\)", "tests", "floor"),
    Check("README.md", r"(\d+) MCP tools", "mcp_tools", "exact"),
    # ROADMAP "Current Status" is the canonical home for status numbers
    Check("ROADMAP.md", r"(\d[\d,]*)\+ unit tests", "tests", "floor"),
    Check("ROADMAP.md", r"Functional with (\d+) tools", "mcp_tools", "exact"),
    Check("ROADMAP.md", r"MCP server with (\d+) tools", "mcp_tools", "exact"),
    Check("ROADMAP.md", r"(\d+)% minimum threshold", "coverage", "exact"),
    # mcp/README is the canonical home for the MCP tool breakdown
    Check("mcp/README.md", r"\*\*Tools:\*\* (\d+) ", "mcp_tools", "exact"),
    # ROADMAP quotes the built-in skill count in two places
    Check("ROADMAP.md", r"(\d+) built-in skills", "skills", "exact"),
]


def _to_int(raw: str) -> int:
    return int(raw.replace(",", ""))


def main() -> int:
    failures: list[str] = []
    values = {name: fn() for name, fn in FACTS.items()}

    for check in CHECKS:
        file_path = REPO_ROOT / check.path
        if not file_path.exists():
            failures.append(f"{check.path}: file not found")
            continue

        text = file_path.read_text(encoding="utf-8")
        matches = re.findall(check.pattern, text)
        if not matches:
            failures.append(
                f"{check.path}: pattern /{check.pattern}/ for '{check.fact}' "
                f"matched nothing (doc reworded? update CHECKS)"
            )
            continue

        actual = values[check.fact]
        for raw in matches:
            stated = _to_int(raw)
            if check.mode == "exact" and stated != actual:
                failures.append(f"{check.path}: states {stated} {check.fact}, source has {actual}")
            elif check.mode == "floor" and stated > actual:
                failures.append(
                    f"{check.path}: states {stated}+ {check.fact}, but source has "
                    f"only {actual} (a '+' floor must be <= the real count)"
                )

    print("Derived from source:")
    print(f"  test functions : {values['tests']}")
    print(f"  coverage gate  : {values['coverage']}%")
    print(f"  MCP tools      : {values['mcp_tools']}")
    print(f"  built-in skills: {values['skills']}")
    print()

    if failures:
        print("Documentation drift detected:")
        for line in failures:
            print(f"  FAIL  {line}")
        print()
        print("Fix the doc, or update the canonical source if the number changed.")
        return 1

    print(f"OK: {len(CHECKS)} doc references consistent with source.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
