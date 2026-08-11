"""CLI: `deepr expert migrate` - move experts into the point-of-view layout.

The old file names were the names of the commands that wrote them. Listing an
expert directory told you which processes had run, not what the expert was, and
two of the names were actively misleading: `brief.json` and `positions.json`
were the same subject stored twice, and `profile.json` and `profile_card.json`
were different things sharing a word.

This moves each expert to names that answer "what is this": `self.json`,
`noticed/`, `hold/current.json` and `hold/history.json`, `became/`, `attend/`,
`met/`. `corpus/` stays, being already named from the expert's side.

Safe to run at any point, and safe to run twice. Readers resolve the old path
when only the old path exists, so an expert migrates without a flag day and the
fleet can be moved in any order. Default is a dry run, because a command that
rearranges 57 directories should have to be asked twice.

$0. Moves files, calls no model, touches no network.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from deepr.cli.colors import console, print_header, print_success, print_warning
from deepr.cli.commands.semantic.experts import expert
from deepr.experts.expert_migration import ExpertMigration, migrate_all
from deepr.experts.paths import canonical_expert_dir


def _fleet_root() -> Path:
    """The directory the experts live in.

    Derived from a canonical expert path rather than reimplemented, so a change
    to where experts are stored cannot leave this command pointing at a stale
    location.
    """
    return canonical_expert_dir("probe").parent


def _report(result: ExpertMigration) -> None:
    console.print(f"[bold]{result.expert_name}[/bold]")
    for old, new in result.moved:
        console.print(f"  {old} -> {new}")
    for dead in result.removed_dead_dirs:
        console.print(f"  [dim]removed empty {dead}/[/dim]")
    for old, new in result.conflicts:
        print_warning(f"  {old} and {new} both exist; left alone, needs a human")
    for dead in result.kept_nonempty_dead_dirs:
        print_warning(f"  {dead}/ is a v1 directory with content in it; left alone")


@expert.command("migrate")
@click.option("--apply", "apply_changes", is_flag=True, help="Actually move files. Without this, only reports.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
def expert_migrate(apply_changes: bool, as_json: bool) -> None:
    """Move experts to the layout named from the expert's point of view."""
    results = migrate_all(_fleet_root(), dry_run=not apply_changes)
    changed = [r for r in results if r.changed]
    attention = [r for r in results if r.needs_attention]

    if as_json:
        click.echo(
            json.dumps(
                {
                    "applied": apply_changes,
                    "experts": len(results),
                    "changed": len(changed),
                    "needs_attention": [r.expert_name for r in attention],
                    "moves": {r.expert_name: r.moved for r in changed},
                    "cost_usd": 0.0,
                },
                indent=2,
            )
        )
        sys.exit(1 if attention else 0)

    print_header("Migrate experts" + ("" if apply_changes else " (dry run)"))
    # Union, not `changed or attention`. That idiom picks the first truthy
    # list, so an expert that only had conflicts was counted in the summary
    # and never printed - the operator was told two needed a human and not
    # which two, which is the silent truncation this command exists to avoid.
    for result in [r for r in results if r.changed or r.needs_attention]:
        _report(result)

    if not changed and not attention:
        print_success(f"All {len(results)} experts already use the current layout.")
        return

    console.print()
    verb = "Moved" if apply_changes else "Would move"
    console.print(f"{verb} files for {len(changed)} of {len(results)} experts.")
    if attention:
        print_warning(f"{len(attention)} need a human; nothing was changed for those.")
    if not apply_changes:
        console.print("[dim]Re-run with --apply to make these changes.[/dim]")
    sys.exit(1 if attention else 0)
