"""`deepr expert cleanup` - repair split expert directories and remove empties.

Historically an expert's profile lived in a slugified directory (``ai_expert/``)
while its beliefs and loop-runs landed in a display-named directory
(``AI Expert/``) - one expert split across two directories (see
docs/design/... / paths.py). This command:

  1. MERGES each split into the single canonical (slug) directory, and
  2. DELETES genuinely-empty experts (no beliefs, conversations, or documents).

Dry-run by default. ``--apply`` backs up the whole experts root first, then
acts (with a confirmation unless ``-y``). Never deletes an expert that has data.
"""

from __future__ import annotations

import json
import shutil
import sys
import tarfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import click

from deepr.cli.colors import console, print_success, print_warning
from deepr.cli.commands.semantic.experts import expert
from deepr.experts.paths import canonical_expert_dir, expert_slug


def archive_dir() -> Path:
    """The gitignored folder where deleted experts are archived (a sibling of
    the experts root, so it is never mistaken for an expert; under ``data/`` and
    thus gitignored)."""
    from deepr.config import experts_root

    return experts_root().parent / "expert-archive"


def archive_expert(name: str) -> Path:
    """Compress an expert's directory into the archive folder and return the path.

    Does not delete the live directory - the caller removes it after a
    successful archive (so a failed archive never loses data).
    """
    src = canonical_expert_dir(name)
    dest_dir = archive_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dest = dest_dir / f"{expert_slug(name)}-{stamp}.tar.gz"
    with tarfile.open(dest, "w:gz") as tar:
        tar.add(src, arcname=src.name)
    return dest


@dataclass
class CleanupPlan:
    merges: list[tuple[Path, Path]] = field(default_factory=list)  # (legacy_dir, canonical_dir)
    deletions: list[Path] = field(default_factory=list)  # canonical dirs with no data
    conflicts: list[str] = field(default_factory=list)


def _belief_count(expert_dir: Path) -> int:
    bf = expert_dir / "beliefs" / "beliefs.json"
    if not bf.exists():
        return 0
    try:
        data = json.loads(bf.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0
    store = data.get("beliefs", data) if isinstance(data, dict) else data
    return len(store.values() if isinstance(store, dict) else store)


def _nonempty_subdir(expert_dir: Path, name: str) -> bool:
    d = expert_dir / name
    return d.is_dir() and any(d.iterdir())


def _has_data(expert_dir: Path) -> bool:
    """An expert has data if it holds beliefs, conversations, or documents."""
    return (
        _belief_count(expert_dir) > 0
        or _nonempty_subdir(expert_dir, "conversations")
        or _nonempty_subdir(expert_dir, "documents")
    )


def build_plan(root: Path) -> CleanupPlan:
    """Plan merges (split dirs) and deletions (empty experts). Pure - no writes."""
    plan = CleanupPlan()
    dirs = [d for d in root.iterdir() if d.is_dir()]
    # Merges: a dir whose name is not its own slug is a legacy/display dir.
    for d in dirs:
        canonical_name = expert_slug(d.name)
        if canonical_name and canonical_name != d.name:
            plan.merges.append((d, root / canonical_name))
    # Deletions: canonical dirs (post-merge) with no data. Simulate the merge by
    # treating a legacy dir's data as belonging to its canonical target.
    has_data_by_canonical: dict[str, bool] = {}
    for d in dirs:
        canonical_name = expert_slug(d.name) or d.name
        has_data_by_canonical[canonical_name] = has_data_by_canonical.get(canonical_name, False) or _has_data(d)
    for canonical_name, has_data in sorted(has_data_by_canonical.items()):
        canonical_dir = root / canonical_name
        if not has_data and canonical_dir.exists():
            plan.deletions.append(canonical_dir)
    return plan


def _merge_tree(src: Path, dst: Path, conflicts: list[str]) -> None:
    """Move files from src into dst, recursing; never overwrite a non-empty file."""
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            _merge_tree(item, target, conflicts)
        elif target.exists() and target.stat().st_size > 0:
            if target.read_bytes() != item.read_bytes():
                conflicts.append(str(target))
        else:
            shutil.move(str(item), str(target))


def _backup(root: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dest = root.parent / f"{root.name}.backup-{stamp}"
    shutil.copytree(root, dest)
    return dest


def _apply_cleanup(root: Path, plan: CleanupPlan, yes: bool) -> None:
    """Back up the experts root, merge split dirs, and delete empty experts."""
    if not yes and not click.confirm("\nBack up the experts root and apply these changes?", default=False):
        print_warning("Cancelled.")
        return

    backup = _backup(root)
    console.print(f"[dim]Backed up experts root to {backup}[/dim]")

    merged = 0
    for legacy, canonical in plan.merges:
        _merge_tree(legacy, canonical, plan.conflicts)
        if not any(p.is_file() for p in legacy.rglob("*")):  # only files matter; empty dirs are fine to drop
            shutil.rmtree(legacy, ignore_errors=True)
            merged += 1
        else:
            print_warning(f"Left {legacy.name} in place (unmerged files remain).")

    # Re-plan deletions against the merged state so we never delete a dir that
    # just received data during the merge above.
    deleted = 0
    for d in build_plan(root).deletions:
        shutil.rmtree(d, ignore_errors=True)
        deleted += 1

    if plan.conflicts:
        print_warning(f"{len(plan.conflicts)} file conflict(s) left untouched (both sides had data):")
        for c in plan.conflicts[:10]:
            console.print(f"  {c}")

    print_success(f"Cleanup complete: merged {merged} split dir(s), deleted {deleted} empty expert(s).")
    if plan.conflicts:
        sys.exit(1)


def _render_plan(plan: CleanupPlan) -> None:
    if plan.merges:
        console.print(f"[bold]Merge {len(plan.merges)} split expert dir(s)[/bold] (display -> canonical slug):")
        for legacy, canonical in plan.merges:
            console.print(f"  {legacy.name}  ->  {canonical.name}/")
    if plan.deletions:
        console.print(f"\n[bold]Delete {len(plan.deletions)} empty expert(s)[/bold] (no beliefs/conversations/docs):")
        for d in plan.deletions:
            console.print(f"  [red]{d.name}[/red]")
    if not plan.merges and not plan.deletions:
        print_success("Nothing to clean - every expert is already a single, populated directory.")


@expert.command(name="cleanup")
@click.option("--apply", "do_apply", is_flag=True, help="Actually perform the cleanup (default is a dry-run).")
@click.option("-y", "--yes", is_flag=True, help="Skip the confirmation prompt when applying.")
def expert_cleanup(do_apply: bool, yes: bool):
    """Merge split expert directories and delete empty experts.

    Dry-run by default. `--apply` backs up the experts root first, then merges
    each split (display-named) directory into its canonical slug directory and
    deletes experts that have no data.

    EXAMPLES:
      deepr expert cleanup              # show what would change
      deepr expert cleanup --apply -y   # back up, then do it
    """
    from deepr.config import experts_root

    root = experts_root()
    if not root.exists():
        print_warning("No experts directory yet - nothing to clean.")
        return

    plan = build_plan(root)
    _render_plan(plan)
    if not plan.merges and not plan.deletions:
        return

    if not do_apply:
        console.print("\n[dim]Dry-run. Re-run with --apply to back up and perform these changes.[/dim]")
        return

    _apply_cleanup(root, plan, yes)


def _run_legacy_state_migration(name: str, do_apply: bool, yes: bool) -> None:
    from deepr.experts.legacy_state_migration import (
        LegacyStateMigrationError,
        migrate_legacy_state,
        plan_legacy_state_migration,
    )

    try:
        plan = plan_legacy_state_migration(name)
    except LegacyStateMigrationError as exc:
        raise click.ClickException(str(exc)) from exc

    if plan.artifact_count == 0 and not plan.prunable_dirs:
        print_success(f"No known legacy state found for {name}.")
        return

    console.print(f"Legacy expert: {plan.legacy_expert_dir}", markup=False)
    console.print(f"Canonical expert: {plan.canonical_expert_dir}", markup=False)
    console.print(
        f"Move {len(plan.moves)} known artifact(s), remove {len(plan.duplicates)} identical duplicate(s), "
        f"prune {len(plan.prunable_dirs)} projected-empty known directory(s), conflicts {len(plan.conflicts)}.",
        markup=False,
    )
    for conflict in plan.conflicts:
        console.print(f"Conflict: {conflict.source.name} ({conflict.reason})", markup=False)
    if plan.conflicts:
        raise click.ClickException("Resolve the listed conflicts before applying; no state was moved.")

    if not do_apply:
        console.print("Dry-run. Re-run with --apply to move only this known legacy state.", style="dim")
        return
    if not yes and not click.confirm("Apply this targeted legacy-state migration?", default=False):
        print_warning("Cancelled.")
        return

    try:
        result = migrate_legacy_state(name)
    except LegacyStateMigrationError as exc:
        raise click.ClickException(str(exc)) from exc
    print_success(
        f"Legacy-state migration complete: moved {len(result.moved)}, deduplicated {len(result.deduplicated)}, "
        f"pruned {len(result.pruned_dirs)} empty directory(s)."
    )


@expert.command(name="migrate-legacy-state")
@click.argument("name")
@click.option("--apply", "do_apply", is_flag=True, help="Move the planned state (default is a dry-run).")
@click.option("-y", "--yes", is_flag=True, help="Skip the confirmation prompt when applying.")
def migrate_legacy_state_cmd(name: str, do_apply: bool, yes: bool) -> None:
    """Move one expert's known state out of a legacy display-name path.

    The preview is limited to known runtime artifact names and projected-empty
    runtime directories for the exact profile identity. Unknown content and
    other experts are never included.

    EXAMPLES:
      deepr expert migrate-legacy-state "Harness Expert"
      deepr expert migrate-legacy-state "Harness Expert" --apply -y
    """
    _run_legacy_state_migration(name, do_apply, yes)


@expert.command(name="migrate-thought-logs", hidden=True)
@click.argument("name")
@click.option("--apply", "do_apply", is_flag=True, help="Move the planned state (default is a dry-run).")
@click.option("-y", "--yes", is_flag=True, help="Skip the confirmation prompt when applying.")
def migrate_thought_logs_cmd(name: str, do_apply: bool, yes: bool) -> None:
    """Compatibility alias for ``migrate-legacy-state``."""
    _run_legacy_state_migration(name, do_apply, yes)
