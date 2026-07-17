"""Append-only operator-attested expert decision outcome commands."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import click
from pydantic import ValidationError

from deepr.cli.colors import print_info, print_success
from deepr.cli.commands.semantic.experts import expert
from deepr.experts.outcomes import (
    ExpertOutcomeDraft,
    ExpertOutcomeStore,
    OutcomeConflictError,
    OutcomeResult,
    OutcomeStorageError,
    build_outcome_summary,
)
from deepr.experts.profile import ExpertStore


def _json_dump(payload: object) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True)


def _require_expert(name: str) -> str:
    profile = ExpertStore().load(name)
    if profile is None:
        raise click.ClickException(f"Expert '{name}' not found")
    return profile.name


@expert.command(name="record-outcome")
@click.argument("name")
@click.option("--decision-id", required=True, help="Stable identifier for the supported decision.")
@click.option("--summary", "decision_summary", required=True, help="Short description of the decision.")
@click.option(
    "--result",
    type=click.Choice(["succeeded", "mixed", "failed", "unresolved"], case_sensitive=True),
    required=True,
    help="Observed result category, supplied through operator attestation.",
)
@click.option("--observation", required=True, help="What happened and why this observation matters.")
@click.option("--observed-at", help="ISO 8601 event timestamp with timezone. Defaults to now.")
@click.option(
    "--attested-by",
    "attested_by",
    required=True,
    help="Operator identity attesting to this observation; identity is not independently verified.",
)
@click.option("--trace-id", help="Optional expert consult trace identifier.")
@click.option("--belief-id", "belief_ids", multiple=True, help="Belief identifier linked to the decision.")
@click.option("--source-ref", "source_refs", multiple=True, help="Source reference linked to the decision.")
@click.option("--evidence-ref", "evidence_refs", multiple=True, help="External outcome evidence reference.")
@click.option("--outcome-id", help="Caller-supplied idempotency identifier.")
@click.option("--supersedes", "supersedes_outcome_id", help="Earlier outcome observation corrected by this one.")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def record_outcome(
    name: str,
    decision_id: str,
    decision_summary: str,
    result: OutcomeResult,
    observation: str,
    observed_at: str | None,
    attested_by: str,
    trace_id: str | None,
    belief_ids: tuple[str, ...],
    source_refs: tuple[str, ...],
    evidence_refs: tuple[str, ...],
    outcome_id: str | None,
    supersedes_outcome_id: str | None,
    json_output: bool,
) -> None:
    """Record one operator-attested outcome without changing expert knowledge."""
    expert_name = _require_expert(name)
    try:
        draft = ExpertOutcomeDraft(
            expert_name=expert_name,
            decision_id=decision_id,
            decision_summary=decision_summary,
            result=result,
            observation=observation,
            observed_at=observed_at or datetime.now(UTC).isoformat(),
            attested_by=attested_by,
            consult_trace_id=trace_id,
            belief_ids=list(belief_ids),
            source_refs=list(source_refs),
            evidence_refs=list(evidence_refs),
            supersedes_outcome_id=supersedes_outcome_id,
        )
        applied = ExpertOutcomeStore().record(draft, outcome_id=outcome_id)
    except (OutcomeConflictError, OutcomeStorageError, ValidationError, ValueError) as exc:
        raise click.ClickException(f"Could not record outcome: {exc}") from exc

    if json_output:
        click.echo(_json_dump(applied.outcome.model_dump(mode="json")))
        return
    if applied.appended:
        print_success(f"Recorded outcome {applied.outcome.outcome_id}.")
    else:
        print_info(f"Outcome {applied.outcome.outcome_id} already matches this observation.")
    click.echo("No beliefs, routing decisions, or external systems were changed.")


@expert.command(name="outcomes")
@click.argument("name")
@click.option("--limit", type=click.IntRange(1, 100), default=20, show_default=True)
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def list_outcomes(name: str, limit: int, json_output: bool) -> None:
    """Show structural outcome history without inferring expert quality."""
    expert_name = _require_expert(name)
    try:
        items = ExpertOutcomeStore().load_all(expert_name)
    except OutcomeStorageError as exc:
        raise click.ClickException(f"Could not load outcomes: {exc}") from exc
    payload = build_outcome_summary(expert_name, items, limit=limit)
    if json_output:
        click.echo(_json_dump(payload))
        return

    click.echo(f"Expert outcomes: {expert_name}")
    click.echo(f"Total observations: {payload['total_outcomes']}")
    click.echo(f"Current outcomes: {payload['active_outcomes']}")
    click.echo(f"Superseded observations: {payload['superseded_outcomes']}")
    counts = payload["result_counts"]
    click.echo(
        "Current results: "
        f"succeeded {counts['succeeded']}, mixed {counts['mixed']}, "
        f"failed {counts['failed']}, unresolved {counts['unresolved']}"
    )
    linkage = payload["linkage"]
    click.echo(
        "Linked records: "
        f"traces {linkage['consult_trace_linked']}, beliefs {linkage['belief_linked']}, "
        f"sources {linkage['source_linked']}, evidence {linkage['evidence_linked']}"
    )
    recent = payload["recent_outcomes"]
    if not recent:
        print_info("No outcomes recorded yet.")
        return
    click.echo("Recent:")
    for item in recent:
        click.echo(f"  {item['outcome_id']} [{item['result']}] {item['decision_id']}: {item['decision_summary']}")


__all__ = ["list_outcomes", "record_outcome"]
