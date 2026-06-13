"""Tests for the Phase Q code-health ratchet scripts.

Fast, pure checks: the file-size guard's logic and registry hygiene, and that
the guard passes on the current tree. The ruff-invoking complexity/security
ratchet is enforced directly by the CI step (running ruff over the whole tree
on every unit run would be needlessly slow), so here we only assert its
baselines are well-formed.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS = _REPO_ROOT / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def file_sizes():
    return _load("check_file_sizes")


@pytest.fixture(scope="module")
def ratchets():
    return _load("check_ratchets")


class TestFileSizeGuard:
    def test_line_count_matches_wc_semantics(self, file_sizes, tmp_path):
        f = tmp_path / "x.py"
        f.write_text("a\nb\nc\n", encoding="utf-8")
        assert file_sizes._line_count(f) == 3

    def test_grandfathered_entries_are_real_and_over_ceiling(self, file_sizes):
        """The debt register must stay honest: every entry exists, is genuinely
        over the ceiling, and has not grown past its recorded cap."""
        for rel, cap in file_sizes.GRANDFATHERED.items():
            path = _REPO_ROOT / rel
            assert path.exists(), f"stale GRANDFATHERED entry (no such file): {rel}"
            assert cap > file_sizes.CEILING, f"{rel} cap {cap} is not above the ceiling - remove it"
            current = file_sizes._line_count(path)
            assert current <= cap, f"{rel} grew to {current} lines, over its cap {cap}"

    def test_guard_passes_on_current_tree(self, file_sizes):
        assert file_sizes.main() == 0


class TestRatchetBaselines:
    def test_baselines_are_positive_ints(self, ratchets):
        assert set(ratchets.BASELINES) == {"C901", "S"}
        for rule, baseline in ratchets.BASELINES.items():
            assert isinstance(baseline, int) and baseline >= 0, rule
