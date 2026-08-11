"""The layout has to be readable mid-migration, or the fleet moves as one.

The whole reason reads fall back to the old path is that 57 experts cannot be
moved atomically, and a reader that only knows the new layout would report an
established expert as empty. These tests hold that property, and the two that
protect against data loss: never overwrite, and never delete a directory that
has something in it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deepr.experts import expert_layout
from deepr.experts.expert_layout import MOVES, part_in, resolve_relative
from deepr.experts.expert_migration import migrate_all, migrate_expert


@pytest.fixture
def expert_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "flooding"
    directory.mkdir()
    return directory


class TestReadingDuringMigration:
    def test_an_unmigrated_expert_is_still_readable(self, expert_dir: Path) -> None:
        (expert_dir / "brief.json").write_text('{"positions": []}', encoding="utf-8")
        assert part_in(expert_dir, "hold_current").name == "brief.json"

    def test_a_migrated_expert_reads_the_new_path(self, expert_dir: Path) -> None:
        (expert_dir / "hold").mkdir()
        (expert_dir / "hold" / "current.json").write_text("{}", encoding="utf-8")
        assert part_in(expert_dir, "hold_current").parent.name == "hold"

    def test_the_new_path_wins_when_both_exist(self, expert_dir: Path) -> None:
        """Otherwise a stale leftover would shadow the current file."""
        (expert_dir / "brief.json").write_text("{}", encoding="utf-8")
        (expert_dir / "hold").mkdir()
        (expert_dir / "hold" / "current.json").write_text("{}", encoding="utf-8")
        assert part_in(expert_dir, "hold_current").parent.name == "hold"

    def test_an_absent_part_resolves_to_the_new_path_for_writing(self, expert_dir: Path) -> None:
        """A writer must never be handed the old location."""
        assert part_in(expert_dir, "hold_current") == expert_dir / "hold" / "current.json"

    def test_an_unknown_part_is_a_typo_not_a_silent_miss(self, expert_dir: Path) -> None:
        with pytest.raises(KeyError):
            part_in(expert_dir, "positions")

    def test_the_expert_root_is_looked_up_late(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Patching the root has to take effect, or tests hit the real fleet."""
        monkeypatch.setattr(expert_layout._paths, "canonical_expert_dir", lambda name: tmp_path / name)
        assert expert_layout.hold_current_path("x") == tmp_path / "x" / "hold" / "current.json"


class TestResolvingByPath:
    def test_a_path_that_moved_falls_back(self, expert_dir: Path) -> None:
        (expert_dir / "study.json").write_text("{}", encoding="utf-8")
        assert resolve_relative(expert_dir, "noticed/current.json").name == "study.json"

    def test_a_path_that_never_moved_resolves_to_itself(self, expert_dir: Path) -> None:
        assert resolve_relative(expert_dir, "corpus/index.jsonl") == expert_dir / "corpus" / "index.jsonl"


class TestMigrating:
    def test_content_survives_the_move(self, expert_dir: Path) -> None:
        (expert_dir / "brief.json").write_text('{"positions": [{"question": "Q"}]}', encoding="utf-8")
        migrate_expert(expert_dir)
        moved = json.loads((expert_dir / "hold" / "current.json").read_text(encoding="utf-8"))
        assert moved["positions"] == [{"question": "Q"}]
        assert not (expert_dir / "brief.json").exists()

    def test_every_declared_move_is_handled(self, expert_dir: Path) -> None:
        """Guards against a part being added to the table and never migrated."""
        for old, _ in MOVES:
            source = expert_dir / old
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("{}", encoding="utf-8")
        result = migrate_expert(expert_dir)
        assert len(result.moved) == len(MOVES)
        for old, new in MOVES:
            assert (expert_dir / new).exists()
            assert not (expert_dir / old).exists()

    def test_running_twice_changes_nothing_the_second_time(self, expert_dir: Path) -> None:
        (expert_dir / "brief.json").write_text("{}", encoding="utf-8")
        migrate_expert(expert_dir)
        assert not migrate_expert(expert_dir).changed

    def test_a_dry_run_touches_nothing(self, expert_dir: Path) -> None:
        (expert_dir / "brief.json").write_text("{}", encoding="utf-8")
        result = migrate_expert(expert_dir, dry_run=True)
        assert result.moved == [("brief.json", "hold/current.json")]
        assert (expert_dir / "brief.json").exists()
        assert not (expert_dir / "hold").exists()

    def test_a_conflict_keeps_both_and_reports(self, expert_dir: Path) -> None:
        """Picking a winner silently is how the wrong file gets kept."""
        (expert_dir / "brief.json").write_text('{"who": "old"}', encoding="utf-8")
        (expert_dir / "hold").mkdir()
        (expert_dir / "hold" / "current.json").write_text('{"who": "new"}', encoding="utf-8")
        result = migrate_expert(expert_dir)
        assert result.conflicts == [("brief.json", "hold/current.json")]
        assert (expert_dir / "brief.json").exists()
        assert result.needs_attention


class TestNotLosingData:
    def test_empty_v1_directories_are_removed(self, expert_dir: Path) -> None:
        (expert_dir / "conversations").mkdir()
        result = migrate_expert(expert_dir)
        assert "conversations" in result.removed_dead_dirs
        assert not (expert_dir / "conversations").exists()

    def test_a_v1_directory_with_content_is_left_alone(self, expert_dir: Path) -> None:
        (expert_dir / "conversations").mkdir()
        (expert_dir / "conversations" / "log.json").write_text("{}", encoding="utf-8")
        result = migrate_expert(expert_dir)
        assert result.kept_nonempty_dead_dirs == ["conversations"]
        assert (expert_dir / "conversations" / "log.json").exists()

    def test_live_v1_storage_is_not_touched_at_all(self, expert_dir: Path) -> None:
        """`beliefs/` and `knowledge/` hold ~4MB across the real fleet.

        They were on the dead list until a dry run showed 38 and 35 experts
        with content in them. They are live storage, so the migration neither
        removes them nor reports them as needing attention.
        """
        for live in ("beliefs", "knowledge"):
            (expert_dir / live).mkdir()
            (expert_dir / live / "data.json").write_text("{}", encoding="utf-8")
        result = migrate_expert(expert_dir)
        assert result.kept_nonempty_dead_dirs == []
        assert not result.needs_attention
        for live in ("beliefs", "knowledge"):
            assert (expert_dir / live / "data.json").exists()

    def test_the_evidence_graph_keeps_its_directory(self, expert_dir: Path) -> None:
        """`graph/` only goes away when the perspective was all that was in it."""
        graph = expert_dir / "graph"
        graph.mkdir()
        (graph / "evidence.json").write_text("{}", encoding="utf-8")
        (graph / "perspective.json").write_text("{}", encoding="utf-8")
        migrate_expert(expert_dir)
        assert (graph / "evidence.json").exists()
        assert (expert_dir / "became" / "perspective.json").exists()

    def test_the_corpus_does_not_move(self, expert_dir: Path) -> None:
        corpus = expert_dir / "corpus"
        corpus.mkdir()
        (corpus / "index.jsonl").write_text("{}\n", encoding="utf-8")
        migrate_expert(expert_dir)
        assert (corpus / "index.jsonl").exists()


class TestMigratingAFleet:
    def test_every_expert_is_visited_in_a_stable_order(self, tmp_path: Path) -> None:
        for name in ("cairn", "aster", "marlow"):
            directory = tmp_path / name
            directory.mkdir()
            (directory / "brief.json").write_text("{}", encoding="utf-8")
        results = migrate_all(tmp_path)
        assert [r.expert_name for r in results] == ["aster", "cairn", "marlow"]
        assert all(r.changed for r in results)

    def test_a_missing_root_is_not_an_error(self, tmp_path: Path) -> None:
        assert migrate_all(tmp_path / "nope") == []


class TestReportingWhatNeedsAHuman:
    """A conflict has to be printed, not just counted.

    The report iterated `changed or attention`, which picks the first truthy
    list rather than the union. An expert that only had conflicts was counted
    in the summary and never named, so the operator was told two needed a
    human and not which two.
    """

    def test_a_conflict_is_listed_even_when_other_experts_moved(self, tmp_path: Path) -> None:
        moved = tmp_path / "moves"
        moved.mkdir()
        (moved / "brief.json").write_text("{}", encoding="utf-8")

        stuck = tmp_path / "conflicts"
        (stuck / "hold").mkdir(parents=True)
        (stuck / "brief.json").write_text("{}", encoding="utf-8")
        (stuck / "hold" / "current.json").write_text("{}", encoding="utf-8")

        results = migrate_all(tmp_path, dry_run=True)
        reportable = [r.expert_name for r in results if r.changed or r.needs_attention]
        assert reportable == ["conflicts", "moves"]

    def test_an_expert_with_only_conflicts_is_reportable(self, expert_dir: Path) -> None:
        (expert_dir / "hold").mkdir()
        (expert_dir / "hold" / "current.json").write_text("{}", encoding="utf-8")
        (expert_dir / "brief.json").write_text("{}", encoding="utf-8")
        result = migrate_expert(expert_dir, dry_run=True)
        assert not result.changed
        assert result.needs_attention
