"""Event-backed repair for expert profile freshness metadata."""

from __future__ import annotations

import json

import click

from deepr.cli.colors import console, print_error, print_info, print_success, print_warning
from deepr.cli.commands.semantic.experts import expert


def _load_reconciliation_state(name: str):
    from deepr.experts.beliefs import BeliefStore
    from deepr.experts.profile import ExpertStore

    store = ExpertStore(create=False)
    expert_dir = store.find_existing_dir(name)
    if expert_dir is None:
        raise click.ClickException(f"Expert not found: {name}")
    profile = store.load(name, persist_migration=False)
    if profile is None or store.find_existing_dir(profile.name) != expert_dir:
        raise click.ClickException(f"Expert profile identity does not match its directory: {name}")
    belief_store = BeliefStore(
        profile.name,
        storage_dir=expert_dir / "beliefs",
        read_only=True,
    )
    return store, profile, belief_store


def _emit_reconciliation_result(plan, payload: dict[str, object], *, json_output: bool) -> None:
    if json_output:
        click.echo(json.dumps(payload, indent=2))
        return
    console.print(f"Evidence events: {plan.evidence_event_count}")
    console.print(f"Latest accepted event: {plan.event_type} {plan.belief_id} at {plan.observed_at.isoformat()}")
    if payload["applied"]:
        print_success("Freshness metadata reconciled from accepted belief-event evidence.")
    elif plan.status == "already_reconciled":
        print_info("Freshness metadata already matches accepted belief-event evidence.")
    else:
        print_warning("Preview only. Run the same command with --apply -y to write profile metadata.")


@expert.command(name="reconcile-freshness")
@click.argument("name")
@click.option("--apply", "apply_change", is_flag=True, help="Write the event-backed profile metadata repair.")
@click.option("--yes", "-y", is_flag=True, help="Apply without an interactive confirmation prompt.")
@click.option("--json", "json_output", is_flag=True, help="Emit the reconciliation plan as JSON.")
def reconcile_freshness(name: str, apply_change: bool, yes: bool, json_output: bool) -> None:
    """Reconcile profile freshness from accepted belief events at zero cost.

    The command reads the append-only belief event log and uses the latest
    created, updated, or revised event for a currently live belief.  It cannot
    infer freshness from a report file, publication date, rejected candidate,
    or missing event.  Preview is the default.

    Example:
      deepr expert reconcile-freshness "My Expert" --apply -y
    """
    from deepr.experts.knowledge_freshness import (
        apply_freshness_reconciliation,
        plan_freshness_reconciliation,
    )

    store, profile, belief_store = _load_reconciliation_state(name)
    plan = plan_freshness_reconciliation(profile, belief_store)
    payload = plan.to_dict()
    payload["applied"] = False

    if plan.observed_at is None:
        if json_output:
            click.echo(json.dumps(payload, indent=2))
        else:
            print_error("No accepted live-belief event can prove a knowledge observation time.")
        raise click.exceptions.Exit(2)

    if apply_change and plan.changed and not yes:
        if not click.confirm(
            f"Advance freshness for '{profile.name}' to {plan.observed_at.isoformat()} from event evidence?",
            default=False,
        ):
            print_warning("Cancelled.")
            return

    if apply_change and plan.changed:
        apply_freshness_reconciliation(profile, plan)
        store.save(profile)
        payload["applied"] = True
        payload["writes"] = "profile_metadata_only"
    elif not apply_change:
        payload["writes"] = "none"

    _emit_reconciliation_result(plan, payload, json_output=json_output)


__all__ = ["reconcile_freshness"]
