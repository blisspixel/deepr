"""Tests for expert cleanup and exact-profile legacy-state migration.

Operates on a temporary experts root built to mirror the real split-directory
bugs (profile in a slug dir, state in a display-named dir).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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


def test_archive_expert_tars_to_gitignored_sibling(tmp_path, monkeypatch):
    import tarfile

    import deepr.config as cfg

    monkeypatch.setattr(cfg, "experts_root", lambda: tmp_path / "experts")
    # An expert dir at the canonical (slug) path with a profile + a belief file.
    _write(tmp_path / "experts" / "my_expert" / "profile.json", {"name": "My Expert"})
    _write(tmp_path / "experts" / "my_expert" / "beliefs" / "beliefs.json", {"beliefs": {"b1": {}}})

    from deepr.cli.commands.semantic.expert_cleanup import archive_expert

    dest = archive_expert("My Expert")

    assert dest.exists() and dest.name.endswith(".tar.gz")
    # Archived to a sibling of the experts root (under data/, gitignored).
    assert dest.parent == tmp_path / "expert-archive"
    with tarfile.open(dest) as tar:
        names = tar.getnames()
    assert any(n.endswith("profile.json") for n in names)
    assert any(n.endswith("beliefs.json") for n in names)
    # Archiving does not remove the live dir (the caller does, after success).
    assert (tmp_path / "experts" / "my_expert" / "profile.json").exists()


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


def test_targeted_legacy_state_migration_moves_only_known_artifacts(tmp_path):
    from deepr.experts.legacy_state_migration import migrate_legacy_state

    name = "Agentic Harness Reliability 2026"
    canonical = tmp_path / "agentic_harness_reliability_2026"
    legacy = tmp_path / name
    _write(canonical / "profile.json", {"name": name})
    thought_log = legacy / "logs" / "thoughts_20260711_120000.jsonl"
    thought_log.parent.mkdir(parents=True)
    thought_log.write_text('{"thought_type":"decision"}\n', encoding="utf-8")
    memory_file = legacy / "memory" / "episodic.json"
    memory_file.parent.mkdir()
    memory_file.write_text("[]", encoding="utf-8")
    empty_graph = legacy / "graph"
    empty_graph.mkdir()
    unrelated_log = legacy / "logs" / "decisions.json"
    unrelated_log.write_text("{}", encoding="utf-8")
    unrelated_expert = tmp_path / "Another Display Expert" / "logs" / "thoughts_20260711_120001.jsonl"
    unrelated_expert.parent.mkdir(parents=True)
    unrelated_expert.write_text("{}\n", encoding="utf-8")

    result = migrate_legacy_state(name, experts_root=tmp_path)

    destination = canonical / "logs" / thought_log.name
    memory_destination = canonical / "memory" / "episodic.json"
    assert result.moved == (destination, memory_destination)
    assert destination.read_text(encoding="utf-8") == '{"thought_type":"decision"}\n'
    assert memory_destination.read_text(encoding="utf-8") == "[]"
    assert not thought_log.exists()
    assert not memory_file.exists()
    assert not empty_graph.exists()
    assert empty_graph in result.pruned_dirs
    assert unrelated_log.exists()
    assert unrelated_expert.exists()


@pytest.mark.parametrize(
    ("relative_dir", "filename"),
    [
        ("memory", "profiles.json"),
        ("memory", "meta_knowledge.json"),
        ("graph", "concepts.json"),
        ("graph", "edges.json"),
        ("cache", "subgraph_cache.json"),
        ("feedback", "feedback.json"),
        ("dspy", "optimized_prompts.json"),
        ("dspy", "optimization_history.json"),
        ("knowledge", "entries.json"),
        ("knowledge", "archive.json"),
    ],
)
def test_targeted_legacy_state_migration_covers_each_known_component(tmp_path, relative_dir, filename):
    from deepr.experts.legacy_state_migration import migrate_legacy_state

    name = "Harness Expert"
    canonical = tmp_path / "harness_expert"
    source = tmp_path / name / relative_dir / filename
    destination = canonical / relative_dir / filename
    _write(canonical / "profile.json", {"name": name})
    source.parent.mkdir(parents=True)
    source.write_text("{}", encoding="utf-8")

    result = migrate_legacy_state(name, experts_root=tmp_path)

    assert result.moved == (destination,)
    assert destination.read_text(encoding="utf-8") == "{}"
    assert not source.exists()


def test_targeted_legacy_state_migration_refuses_different_collision(tmp_path):
    from deepr.experts.legacy_state_migration import (
        LegacyStateMigrationError,
        migrate_legacy_state,
        plan_legacy_state_migration,
    )

    name = "Agentic Harness Reliability 2026"
    canonical = tmp_path / "agentic_harness_reliability_2026"
    legacy_log = tmp_path / name / "logs" / "thoughts_20260711_120000.jsonl"
    canonical_log = canonical / "logs" / legacy_log.name
    _write(canonical / "profile.json", {"name": name})
    legacy_log.parent.mkdir(parents=True)
    legacy_log.write_text("legacy\n", encoding="utf-8")
    canonical_log.parent.mkdir(parents=True)
    canonical_log.write_text("canonical\n", encoding="utf-8")

    plan = plan_legacy_state_migration(name, experts_root=tmp_path)

    assert len(plan.conflicts) == 1
    with pytest.raises(LegacyStateMigrationError, match="no state was moved"):
        migrate_legacy_state(name, experts_root=tmp_path)
    assert legacy_log.read_text(encoding="utf-8") == "legacy\n"
    assert canonical_log.read_text(encoding="utf-8") == "canonical\n"


def test_targeted_legacy_state_migration_requires_exact_profile_identity(tmp_path):
    from deepr.experts.legacy_state_migration import LegacyStateMigrationError, plan_legacy_state_migration

    _write(tmp_path / "harness_expert" / "profile.json", {"name": "Harness Expert"})

    with pytest.raises(LegacyStateMigrationError, match="exactly match"):
        plan_legacy_state_migration("HARNESS EXPERT", experts_root=tmp_path)
    with pytest.raises(LegacyStateMigrationError, match="one non-empty"):
        plan_legacy_state_migration("../Harness Expert", experts_root=tmp_path)


def test_targeted_legacy_state_migration_deduplicates_identical_copy(tmp_path):
    from deepr.experts.legacy_state_migration import migrate_legacy_state

    name = "Harness Expert"
    canonical = tmp_path / "harness_expert"
    source = tmp_path / name / "logs" / "thoughts_20260711_120000.jsonl"
    destination = canonical / "logs" / source.name
    _write(canonical / "profile.json", {"name": name})
    source.parent.mkdir(parents=True)
    destination.parent.mkdir(parents=True)
    source.write_text("same\n", encoding="utf-8")
    destination.write_text("same\n", encoding="utf-8")

    result = migrate_legacy_state(name, experts_root=tmp_path)

    assert result.moved == ()
    assert result.deduplicated == (destination,)
    assert not source.exists()
    assert destination.read_text(encoding="utf-8") == "same\n"


def test_targeted_legacy_state_migration_prunes_only_known_empty_dirs(tmp_path):
    from deepr.experts.legacy_state_migration import migrate_legacy_state

    name = "Harness Expert"
    _write(tmp_path / "harness_expert" / "profile.json", {"name": name})
    legacy = tmp_path / name
    (legacy / "memory").mkdir(parents=True)
    (legacy / "graph").mkdir()

    result = migrate_legacy_state(name, experts_root=tmp_path)

    assert result.moved == ()
    assert legacy / "memory" in result.pruned_dirs
    assert legacy / "graph" in result.pruned_dirs
    assert legacy in result.pruned_dirs
    assert not legacy.exists()


def test_targeted_legacy_state_command_is_dry_run_by_default(tmp_path, monkeypatch):
    from click.testing import CliRunner

    import deepr.config as cfg
    from deepr.cli.commands.semantic.expert_cleanup import migrate_legacy_state_cmd, migrate_thought_logs_cmd

    name = "Agentic Harness Reliability 2026"
    canonical = tmp_path / "agentic_harness_reliability_2026"
    source = tmp_path / name / "logs" / "thoughts_20260711_120000.jsonl"
    _write(canonical / "profile.json", {"name": name})
    source.parent.mkdir(parents=True)
    source.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(cfg, "experts_root", lambda: tmp_path)

    alias_preview = CliRunner().invoke(migrate_thought_logs_cmd, [name])
    preview = CliRunner().invoke(migrate_legacy_state_cmd, [name])

    assert alias_preview.exit_code == 0, alias_preview.output
    assert "Dry-run" in alias_preview.output
    assert preview.exit_code == 0, preview.output
    assert "Dry-run" in preview.output
    assert source.exists()
    assert not (canonical / "logs" / source.name).exists()

    applied = CliRunner().invoke(migrate_legacy_state_cmd, [name, "--apply", "-y"])
    assert applied.exit_code == 0, applied.output
    assert not source.exists()
    assert (canonical / "logs" / source.name).exists()


def test_targeted_legacy_state_command_is_visible_and_alias_is_hidden():
    from click.testing import CliRunner

    from deepr.cli.commands.semantic.experts import expert

    result = CliRunner().invoke(expert, ["--help"])

    assert result.exit_code == 0, result.output
    assert "migrate-legacy-state" in result.output
    assert "migrate-thought-logs" not in result.output
