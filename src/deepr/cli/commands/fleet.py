"""`deepr fleet` - roster health and host-schedule recipe workflows.

``fleet status`` provides one read-only, $0 view of failures, waits, refresh work,
and bounded spend evidence. ``fleet install-schedule`` previews or explicitly
writes host scheduler recipes but never registers host state or runs maintenance.

This is the agent-run health view; ``deepr capacity fleet`` is the separate
plan-quota CLI-backend view. Design: docs/design/expert-fleet.md.
"""

from __future__ import annotations

import json as _json
import sys
from pathlib import Path
from typing import Any

import click
from rich.markup import escape

from deepr.cli.colors import console, print_error, print_success, print_warning
from deepr.experts.fleet_schedule import ScheduleRecipe, ScheduleSpec, render_recipe, resolve_platform
from deepr.experts.fleet_status import build_fleet_status_rollup, fleet_needs_attention
from deepr.utils.atomic_io import atomic_write_text


@click.group(name="fleet")
def fleet() -> None:
    """Roster-wide expert health and host-schedule recipes ($0)."""


def _row_tag(row: dict[str, Any]) -> str:
    if row.get("state_errors"):
        return "[red]UNREADABLE[/red]"
    if row["attention"] is True:
        return "[red]FAILED[/red]"
    if row["waiting"]:
        return "[yellow]waiting[/yellow]"
    if row["refresh_due"]:
        return "[cyan]refresh due[/cyan]"
    if not row["has_runs"]:
        return "[dim]never run[/dim]"
    return "[green]ok[/green]"


def _row_detail(row: dict[str, Any]) -> str:
    if "runs_unreadable" in row.get("state_errors", []):
        return "loop history unavailable"
    last = row["last_run"]
    if not last:
        return "no runs recorded"
    return (
        f"{last['loop_type']} {last['status']} "
        f"(+{last['accepted_changes']}/-{last['rejected_changes']}, "
        f"${last['budget_spent']:.2f} {last['capacity_source']})"
    )


def _terminal_safe_text(value: object) -> str:
    """Render stored text on one visible Rich-safe terminal line."""
    text = str(value)
    visible = "".join(character if character.isprintable() else ascii(character)[1:-1] for character in text)
    return escape(visible)


def _print_row_extras(row: dict[str, Any]) -> None:
    state_errors = row.get("state_errors", [])
    if state_errors:
        labels = {
            "runs_unreadable": "loop history",
            "subscriptions_unreadable": "subscriptions",
        }
        unavailable = ", ".join(labels[code] for code in state_errors if code in labels)
        console.print(f"      [red]state unavailable:[/red] {_terminal_safe_text(unavailable)}")
    if isinstance(row["refresh_due"], int) and row["refresh_due"] > 0:
        topics = ", ".join(_terminal_safe_text(topic) for topic in (row["due_topics"] or [])[:5])
        more = "..." if row["refresh_due"] > 5 else ""
        console.print(f"      [cyan]refresh due:[/cyan] {row['refresh_due']} topic(s) - {topics}{more}")
    if row["waiting_next_action"]:
        title = _terminal_safe_text(row["waiting_next_action"].get("title", ""))
        console.print(f"      [yellow]waiting:[/yellow] {title}")
    if row["attention"] is True and row["last_failure"]:
        reason = row["last_failure"].get("failure_reason") or row["last_failure"].get("stop_reason") or ""
        console.print(f"      [red]last failure:[/red] {_terminal_safe_text(reason)}")


def _render_human(payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    rows = payload["experts"]

    if not payload.get("complete", True):
        errors = payload.get("state_errors", {})
        labels = {
            "profiles": ("profile source", "profile sources"),
            "runs": ("loop history", "loop histories"),
            "subscriptions": ("subscription source", "subscription sources"),
        }
        details = [
            f"{count} unreadable {labels[kind][count != 1]}"
            for kind, count in errors.items()
            if count and kind in labels
        ]
        suffix = f": {', '.join(details)}" if details else ""
        print_error(f"Fleet status is incomplete{suffix}.")

    if not rows and payload.get("complete", True):
        print_warning("No experts yet. Create one with `deepr expert make`.")
        return

    for row in rows:
        expert = _terminal_safe_text(row["expert"])
        detail = _terminal_safe_text(_row_detail(row))
        console.print(f"  {_row_tag(row)}  [bold]{expert}[/bold]  [dim]{detail}[/dim]")
        _print_row_extras(row)

    if rows or not payload.get("complete", True):
        expert_label = "expert" if summary["experts"] == 1 else "experts"
        state_error_count = summary.get("state_errors", 0)
        state_error_label = "source" if state_error_count == 1 else "sources"
        state_error_summary = (
            f" · {state_error_count} unreadable state {state_error_label}" if state_error_count else ""
        )
        if payload.get("complete", True):
            console.print(
                f"\n[bold]{summary['experts']} readable {expert_label}[/bold] · "
                f"{summary['attention']} failed · {summary['waiting']} waiting · "
                f"{summary['refresh_due']} refresh-due · {summary['never_run']} never-run · "
                f"${summary['budget_spent_window_total']:.2f} spent (window)"
            )
        else:
            observed = summary["observed"]
            console.print(
                f"\n[bold]{summary['experts']} readable {expert_label}[/bold] · "
                f"observed readable state: {observed['attention']} failed · "
                f"{observed['waiting']} waiting · {observed['refresh_due']} refresh-due · "
                f"{observed['never_run']} never-run · "
                f"${observed['budget_spent_window_total']:.2f} spent (window)"
                f"{state_error_summary}"
            )
    if not payload.get("complete", True):
        for ref in payload.get("state_error_refs", []):
            expert = f"{ref['expert']}: " if ref.get("expert") else ""
            console.print(
                f"      [red]unreadable source:[/red] {_terminal_safe_text(expert)}{_terminal_safe_text(ref['source'])}"
            )
        omitted = payload.get("state_error_refs_omitted", 0)
        if omitted:
            console.print(f"      [red]{omitted} additional unreadable source(s) omitted[/red]")
        console.print("[dim]Inspect the listed source under the configured experts root, repair it, then retry.[/dim]")


@fleet.command(name="status")
@click.option("--json", "json_output", is_flag=True, help="Emit the versioned machine-readable payload.")
@click.option("--limit", default=20, show_default=True, help="Loop runs to summarize per expert.")
def status(json_output: bool, limit: int) -> None:
    """Show fleet health across all experts.

    Read-only and $0: folds each expert's loop-run history and refresh cadence.
    Exits non-zero when any expert's latest run failed or durable state was
    unreadable, so a scheduler can use it as a cheap fail-closed watchdog.

    EXAMPLES:
      deepr fleet status
      deepr fleet status --json
    """
    if limit < 1:
        print_warning("--limit must be positive.")
        sys.exit(2)

    payload = build_fleet_status_rollup(limit=limit)

    if json_output:
        click.echo(_json.dumps(payload, indent=2))
    else:
        _render_human(payload)
        if not fleet_needs_attention(payload) and payload["experts"]:
            print_success("No latest-run failures or unreadable expert state detected.")

    if fleet_needs_attention(payload):
        sys.exit(1)


def _render_recipe_to_stdout(recipe: ScheduleRecipe) -> None:
    console.print("[bold]Schedule recipe preview[/bold]")
    click.echo(f"Resolved target: {recipe.platform}")
    for filename, content in recipe.files.items():
        console.print(f"[bold]# {filename}[/bold]")
        click.echo(content)
    if recipe.inline:
        console.print("[bold]# crontab line[/bold]")
        click.echo(recipe.inline)
    print_warning("Preview only: no files were written and no host schedule was installed.")
    if recipe.files:
        click.echo("Next: rerun this command with --output DIRECTORY to write the recipe files.")
        click.echo("Install instructions are shown only after all requested files are written.")
        return
    console.print("\n[bold]Install[/bold]")
    click.echo(recipe.instructions)


def _resolve_schedule_output_directory(output: Path) -> Path:
    if any(not character.isprintable() for character in str(output)):
        raise ValueError("--output must not contain control characters or line breaks")
    return output.resolve()


def _schedule_output_files(recipe: ScheduleRecipe, *, name: str) -> dict[str, str]:
    files = dict(recipe.files)
    if recipe.inline:
        files[f"{name}.cron"] = recipe.inline + "\n"
    return files


def _schedule_output_targets(output_directory: Path, files: dict[str, str]) -> dict[Path, str]:
    targets: dict[Path, str] = {}
    for filename, content in files.items():
        target = output_directory / filename
        if target.parent.resolve() != output_directory:
            raise ValueError("recipe output must remain directly inside --output")
        targets[target] = content
    return targets


class _ScheduleOutputCollisionError(Exception):
    """An existing recipe needs explicit replacement authority."""


def _write_schedule_recipe(targets: dict[Path, str], *, force: bool) -> list[str]:
    collisions = sorted(path.name for path in targets if path.exists())
    if collisions and not force:
        names = ", ".join(collisions)
        raise _ScheduleOutputCollisionError(
            f"Refusing to replace existing schedule recipe file(s): {names}. "
            "Rerun with --force only after reviewing those files."
        )

    written: list[str] = []
    for path, content in targets.items():
        try:
            atomic_write_text(path, content, encoding="utf-8", overwrite=force)
        except FileExistsError:
            raise _ScheduleOutputCollisionError(
                f"Refusing to replace existing schedule recipe file: {path.name}. "
                "Another writer may have created it during output; existing content was preserved. "
                "Review the directory and rerun with --force only if replacement is intended."
            ) from None
        written.append(path.name)
    return written


@fleet.command(name="install-schedule")
@click.option(
    "--platform",
    type=click.Choice(["auto", "windows", "cron", "systemd"]),
    default="auto",
    show_default=True,
    help="Host scheduler to target (auto detects this OS).",
)
@click.option(
    "--command",
    default="deepr fleet status",
    show_default=True,
    help=(
        "The deepr command to schedule. The default is a read-only health check; "
        "use 'deepr expert sync-all --scheduled -y' for maintenance."
    ),
)
@click.option("--cadence", type=click.Choice(["hourly", "daily"]), default="daily", show_default=True)
@click.option("--at", default="03:00", show_default=True, help="HH:MM local time (daily cadence).")
@click.option("--name", default="deepr-fleet", show_default=True, help="Scheduled task/unit name.")
@click.option(
    "--jitter-minutes",
    type=int,
    default=15,
    show_default=True,
    help="Random start spread so a roster does not stampede a rate-limited backend.",
)
@click.option(
    "--output",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Write recipe files to this directory instead of printing them.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Replace existing recipe files in --output after explicit review.",
)
def install_schedule(
    platform: str,
    command: str,
    cadence: str,
    at: str,
    name: str,
    jitter_minutes: int,
    output: Path | None,
    force: bool,
) -> None:
    """Emit a host-scheduler recipe to run a deepr command on a cadence.

    This command never registers host state. Without --output it previews the
    recipe. With --output it writes the artifacts and then prints output-aware
    manual installation and verification steps. The recipe is tuned for catch-up,
    not punctuality: a sleeping host may run the job after its next wake.

    \b
    Examples:
      deepr fleet install-schedule
      deepr fleet install-schedule --command "deepr expert sync-all --scheduled -y"
      deepr fleet install-schedule --platform systemd --at 02:30 --output ./schedule
    """
    if force and output is None:
        print_error("--force requires --output because previews never replace files")
        sys.exit(2)

    try:
        target = resolve_platform(platform, system=sys.platform)
        spec = ScheduleSpec(command=command, cadence=cadence, at=at, name=name, jitter_minutes=jitter_minutes)
        output_directory = _resolve_schedule_output_directory(output) if output is not None else None
        recipe = render_recipe(target, spec, output_directory=output_directory)
    except ValueError as exc:
        print_error(str(exc))
        sys.exit(2)
    except OSError:
        print_error("Could not resolve --output. No recipe files or host schedule were created.")
        sys.exit(1)

    if output_directory is not None:
        try:
            files = _schedule_output_files(recipe, name=name)
            targets = _schedule_output_targets(output_directory, files)
            output_directory.mkdir(parents=True, exist_ok=True)
            written = _write_schedule_recipe(targets, force=force)
        except ValueError as exc:
            print_error(str(exc))
            sys.exit(2)
        except _ScheduleOutputCollisionError as exc:
            print_error(str(exc))
            sys.exit(2)
        except OSError:
            print_error(
                "Could not write schedule recipe files. No host schedule was installed; "
                "the output directory may be incomplete. Check permissions and free space, "
                "review any files present, and retry."
            )
            sys.exit(1)
        safe_output = _terminal_safe_text(output_directory)
        print_success(f"Wrote {', '.join(written)} to {safe_output}")
        click.echo("Recipe files are ready; the host schedule was not installed.")
        console.print("\n[bold]Install and verify[/bold]")
        click.echo(recipe.instructions)
        return

    _render_recipe_to_stdout(recipe)
