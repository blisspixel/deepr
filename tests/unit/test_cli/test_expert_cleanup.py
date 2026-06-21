"""Tests for `deepr expert cleanup` - merge split dirs + delete empty experts.

Operates on a temporary experts root built to mirror the real split-directory
bug (profile in a slug dir, beliefs in a display-named dir).
"""

from __future__ import annotations

import json
from pathlib import Path

from deepr.cli.commands.semantic.expert_cleanup import build_plan


def _write(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj), encoding="utf-8")


def _make_split_expert(root: Path, display: str, slug: str, n_beliefs: int) -> None:
    """Profile in the slug dir; beliefs in the display dir - the bug's shape."""
    _write(root / slug / "profile.json", {"name": display})
    if n_beliefs:
        _write(root / display / "beliefs" / "beliefs.json", {"beliefs": {f"b{i}": {} for i in range(n_beliefs)}})


def test_plan_pairs_split_dirs_and_keeps_populated(tmp_path):
    _make_split_expert(tmp_path, "AI Expert", "ai_expert", n_beliefs=5)
    plan = build_plan(tmp_path)
    # The display dir is planned to merge into the canonical slug dir.
    assert (tmp_path / "AI Expert", tmp_path / "ai_expert") in plan.merges
    # A populated expert is never deleted.
    assert tmp_path / "ai_expert" not in plan.deletions


def test_plan_deletes_empty_expert(tmp_path):
    # Profile-only, no beliefs anywhere -> empty -> delete candidate.
    _write(tmp_path / "empty_expert" / "profile.json", {"name": "Empty Expert"})
    plan = build_plan(tmp_path)
    assert tmp_path / "empty_expert" in plan.deletions


def test_plan_does_not_delete_when_beliefs_in_split_display_dir(tmp_path):
    # The canonical slug dir is empty, but its display twin holds the beliefs;
    # the expert must NOT be deleted (data lives in the split dir).
    _make_split_expert(tmp_path, "Real Expert", "real_expert", n_beliefs=12)
    plan = build_plan(tmp_path)
    assert tmp_path / "real_expert" not in plan.deletions
    assert tmp_path / "Real Expert" not in plan.deletions


def test_apply_merges_and_deletes(tmp_path, monkeypatch):
    import deepr.config as cfg

    _make_split_expert(tmp_path, "AI Expert", "ai_expert", n_beliefs=5)
    _write(tmp_path / "empty_expert" / "profile.json", {"name": "Empty Expert"})
    monkeypatch.setattr(cfg, "experts_root", lambda: tmp_path)

    from click.testing import CliRunner

    from deepr.cli.commands.semantic.expert_cleanup import expert_cleanup

    result = CliRunner().invoke(expert_cleanup, ["--apply", "-y"])
    assert result.exit_code == 0, result.output

    # Merged: beliefs now live in the canonical slug dir; display dir is gone.
    assert (tmp_path / "ai_expert" / "beliefs" / "beliefs.json").exists()
    assert not (tmp_path / "AI Expert").exists()
    assert (tmp_path / "ai_expert" / "profile.json").exists()
    # Deleted: the empty expert is gone.
    assert not (tmp_path / "empty_expert").exists()
    # A backup was created alongside the root.
    assert any(p.name.startswith(f"{tmp_path.name}.backup-") for p in tmp_path.parent.iterdir())


def test_dry_run_changes_nothing(tmp_path, monkeypatch):
    import deepr.config as cfg

    _make_split_expert(tmp_path, "AI Expert", "ai_expert", n_beliefs=5)
    monkeypatch.setattr(cfg, "experts_root", lambda: tmp_path)

    from click.testing import CliRunner

    from deepr.cli.commands.semantic.expert_cleanup import expert_cleanup

    result = CliRunner().invoke(expert_cleanup, [])  # no --apply
    assert result.exit_code == 0
    assert (tmp_path / "AI Expert").exists()  # untouched
    assert not any(p.name.startswith(f"{tmp_path.name}.backup-") for p in tmp_path.parent.iterdir())
