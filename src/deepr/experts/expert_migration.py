"""Move an expert from the command-named layout to the point-of-view one.

Moves rather than copies. A copy would leave two files that both look current
and immediately drift, and the next reader has no way to tell which one is
authoritative - the exact confusion `brief.json` and `positions.json` already
caused. The content is preserved by the move and the prior state is in git, so
there is nothing a copy would protect that is not already protected.

Three properties this holds to:

**Idempotent.** Running it twice is a no-op, because a move whose source is
gone is skipped rather than failing. Half a migration is therefore recoverable
by running it again.

**Never overwrites.** If the destination already exists the source is left
alone and the conflict is reported. That case means someone wrote the new
layout and the old file separately, and picking a winner silently is how the
wrong one gets kept.

**Reports, does not assume.** `plan()` says what would happen without touching
anything, so the fleet can be inspected before it moves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from deepr.experts.expert_layout import DEAD_V1_DIRS, MOVES


@dataclass
class ExpertMigration:
    """What happened, or would happen, to one expert."""

    expert_name: str
    moved: list[tuple[str, str]] = field(default_factory=list)
    conflicts: list[tuple[str, str]] = field(default_factory=list)
    """Both paths exist. Not migrated; needs a human."""
    removed_dead_dirs: list[str] = field(default_factory=list)
    kept_nonempty_dead_dirs: list[str] = field(default_factory=list)
    """A v1 directory that had something in it. Left alone deliberately."""

    @property
    def changed(self) -> bool:
        return bool(self.moved or self.removed_dead_dirs)

    @property
    def needs_attention(self) -> bool:
        return bool(self.conflicts or self.kept_nonempty_dead_dirs)


def _dir_is_empty(path: Path) -> bool:
    return path.is_dir() and not any(path.iterdir())


def _move_files(expert_dir: Path, result: ExpertMigration, *, dry_run: bool) -> None:
    """Move each renamed artifact, recording conflicts rather than resolving them."""
    for old_name, new_name in MOVES:
        source = expert_dir / old_name
        if not source.exists():
            continue
        destination = expert_dir / new_name
        if destination.exists():
            result.conflicts.append((old_name, new_name))
            continue
        result.moved.append((old_name, new_name))
        if not dry_run:
            destination.parent.mkdir(parents=True, exist_ok=True)
            source.replace(destination)


def _prune_empty_dirs(expert_dir: Path, result: ExpertMigration, *, dry_run: bool) -> None:
    """Remove the directories that are empty, and report the ones that are not.

    `graph/` is included because moving perspective.json out empties it when the
    evidence graph was never built, and the migration should not trade one set
    of empty directories for another.
    """
    for dead in (*DEAD_V1_DIRS, "graph"):
        candidate = expert_dir / dead
        if not candidate.is_dir():
            continue
        if _dir_is_empty(candidate):
            result.removed_dead_dirs.append(dead)
            if not dry_run:
                candidate.rmdir()
        elif dead != "graph":
            result.kept_nonempty_dead_dirs.append(dead)


def migrate_expert(expert_dir: Path, *, dry_run: bool = False) -> ExpertMigration:
    """Move one expert's files into the new layout.

    `dry_run` reports the same result without touching the filesystem, so the
    caller can show a plan and the plan is produced by the code that does the
    work rather than by a second description of it that can fall out of date.
    """
    result = ExpertMigration(expert_name=expert_dir.name)
    _move_files(expert_dir, result, dry_run=dry_run)
    _prune_empty_dirs(expert_dir, result, dry_run=dry_run)
    return result


def migrate_all(experts_root: Path, *, dry_run: bool = False) -> list[ExpertMigration]:
    """Migrate every expert under a root, in a stable order.

    Sorted so two runs over the same fleet produce comparable output; an
    operator diffing a dry run against the real one should see ordering noise
    from neither.
    """
    if not experts_root.is_dir():
        return []
    return [
        migrate_expert(child, dry_run=dry_run)
        for child in sorted(experts_root.iterdir())
        if child.is_dir() and not child.name.startswith(".")
    ]
