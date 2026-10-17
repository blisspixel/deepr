"""Read an expert's world-time clock, or admit one explicit end or affirmation.

Inspection is the default and writes nothing. Closing or affirming a claim
is an operator write with a retained reason. Neither command calls a model
or spends from the wallet.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from deepr.cli.colors import console, print_error, print_success
from deepr.cli.commands.semantic.experts import expert
from deepr.experts.beliefs import BeliefStore, BeliefStoreError
from deepr.experts.currency_inspection import inspect_currency
from deepr.experts.profile import ExpertStore
from deepr.experts.world_validity import (
    WorldValidityError,
    affirm_in_force,
    close_claim,
    parse_utc,
)


def _resolve_expert(name: str) -> tuple[str, Path]:
    store = ExpertStore(create=False)
    expert_dir = store.find_existing_dir(name)
    if expert_dir is None:
        raise click.ClickException(f"Expert not found: {name}")
    profile = store.load(name, persist_migration=False)
    if profile is None or store.find_existing_dir(profile.name) != expert_dir:
        raise click.ClickException(f"Expert profile identity does not match its directory: {name}")
    return profile.name, expert_dir


def _writable_beliefs(name: str, expert_dir: Path) -> BeliefStore:
    return BeliefStore(name, storage_dir=expert_dir / "beliefs", read_only=False)


@expert.command(name="currency")
@click.argument("name")
@click.option("--question", default="", help="Optional question to bind into the packet hash. It is not judged.")
@click.option("--json", "json_output", is_flag=True, help="Emit the inspection packet as JSON.")
def currency(name: str, question: str, json_output: bool) -> None:
    """Show whether stored claims have a world-time end. Writes nothing.

    A decayed confidence and a recent file date stay visible as ranks and
    timestamps. They are not a statement that the claim is current.

    Example:
      deepr expert currency "My Expert" --json
    """
    expert_name, expert_dir = _resolve_expert(name)
    packet = inspect_currency(expert_dir, expert_name, question=question or None)
    if json_output:
        click.echo(json.dumps(packet, indent=2, sort_keys=True))
    else:
        if not packet["belief_store_readable"]:
            print_error(f"{packet['expert']}: belief store is unreadable. No world-time status was projected.")
        else:
            world = packet.get("world_validity") or {}
            counts = world.get("live_counts") or {}
            console.print(f"[bold]{packet['expert']}[/bold]")
            console.print("Live check: not examined. Further research: not judged.")
            console.print(
                "World time: "
                f"{counts.get('live', 0)} live, "
                f"{counts.get('unknown', 0)} unknown, "
                f"{counts.get('in_force', 0)} explicitly in force."
            )
            closed_on_live = int(counts.get("closed_mark_on_live_belief", 0))
            if closed_on_live:
                console.print(f"Closed marks still on live beliefs: {closed_on_live}.")
                console.print("Those rows are defects, not current claims.")
            console.print(f"Closed ends: {len(world.get('closed_ends') or [])}.")
            console.print(
                f"Store retirements without a world end: {len(world.get('store_retirements_without_world_end') or [])}."
            )
            console.print(f"Open contradictions: {len(world.get('open_contradictions') or [])}.")
            console.print("Decay is a rank. It does not record when a claim stopped being true.")
        if not packet["files_unchanged"]:
            print_error("Inspection changed canonical files. Treat the packet as failed.")
            raise click.exceptions.Exit(1)
    if not packet["belief_store_readable"] or not packet["files_unchanged"]:
        raise click.exceptions.Exit(2)


@expert.command(name="close-claim")
@click.argument("name")
@click.option("--belief-id", required=True, help="Live belief to close.")
@click.option("--ended-at", required=True, help="Timezone-aware instant when the claim stopped holding.")
@click.option(
    "--basis",
    required=True,
    type=click.Choice(["observed", "source_resolved"]),
    help="Where the end instant came from. Decay is not a basis.",
)
@click.option("--evidence", required=True, help="Retained reason, including the source that dated the end.")
@click.option("--yes", is_flag=True, help="Write the world end. Without this flag the command refuses.")
def close_claim_cmd(name: str, belief_id: str, ended_at: str, basis: str, evidence: str, yes: bool) -> None:
    """Record when one live claim stopped being true, and keep the old text.

    Example:
      deepr expert close-claim "My Expert" --belief-id abc \\
        --ended-at 2026-10-01T00:00:00+00:00 --basis observed \\
        --evidence "Vendor changelog." --yes
    """
    if not yes:
        raise click.UsageError("Refusing to close a claim without --yes.")
    expert_name, expert_dir = _resolve_expert(name)
    try:
        ended = parse_utc(ended_at, field_name="ended_at")
        change = close_claim(
            _writable_beliefs(expert_name, expert_dir),
            belief_id,
            ended_at=ended,
            basis=basis,
            evidence=evidence,
        )
    except (WorldValidityError, BeliefStoreError) as exc:
        raise click.ClickException(str(exc)) from exc
    print_success(
        f"Closed {change.belief_id} at {change.invalidated_at.isoformat() if change.invalidated_at else 'unknown'}."
    )
    console.print("The previous claim remains in the archival snapshot. Consult was not run.")


@expert.command(name="affirm-claim")
@click.argument("name")
@click.option("--belief-id", required=True, help="Live belief to mark in force.")
@click.option("--evidence", required=True, help="Retained reason for the affirmation.")
@click.option("--valid-from", default="", help="Optional timezone-aware start. Omitted means the start is unknown.")
@click.option("--yes", is_flag=True, help="Write the in-force mark. Without this flag the command refuses.")
def affirm_claim_cmd(name: str, belief_id: str, evidence: str, valid_from: str, yes: bool) -> None:
    """Mark one live claim in force. Confidence and the decay clock stay put.

    Example:
      deepr expert affirm-claim "My Expert" --belief-id abc --evidence "Primary manual, section 4." --yes
    """
    if not yes:
        raise click.UsageError("Refusing to affirm a claim without --yes.")
    expert_name, expert_dir = _resolve_expert(name)
    started = parse_utc(valid_from, field_name="valid_from") if valid_from.strip() else None
    try:
        change = affirm_in_force(
            _writable_beliefs(expert_name, expert_dir),
            belief_id,
            evidence=evidence,
            valid_from=started,
        )
    except (WorldValidityError, BeliefStoreError) as exc:
        raise click.ClickException(str(exc)) from exc
    print_success(f"Marked {change.belief_id} in force. Confidence was not changed.")
