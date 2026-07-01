"""Health-check archive execution helpers."""

from __future__ import annotations

import json as _json
from typing import Any

import click

from deepr.cli.colors import console, print_error, print_header, print_success


def archive_stale_beliefs(name: str, *, yes: bool, json_output: bool, scheduled: bool) -> None:
    """Execute the health-check archive-candidates action."""
    import sys

    from deepr.cli.commands.semantic.expert_health_loop import record_completed_health_archive
    from deepr.experts.beliefs import BeliefStore
    from deepr.experts.paths import canonical_expert_dir

    beliefs_dir = canonical_expert_dir(name) / "beliefs"
    if not beliefs_dir.exists():
        print_error(f"No belief store found for expert: {name}")
        sys.exit(2)

    belief_store = BeliefStore(name)
    candidates = belief_store.archive_candidates()

    if not candidates:
        loop_run = record_completed_health_archive(name, archived_count=0)
        if json_output:
            click.echo(_json.dumps({"expert": name, "archived": [], "count": 0, "loop_run": loop_run.to_dict()}))
        else:
            print_success("No beliefs eligible for lifecycle archival.")
        return

    if scheduled and not yes:
        from deepr.cli.commands.semantic.expert_health_schedule import emit_scheduled_archive_confirmation

        emit_scheduled_archive_confirmation(name, candidates, json_output=json_output)
        return

    if not json_output:
        print_header(f"Archive candidates: {name}")
        for belief in candidates:
            console.print(
                f"  - {belief.claim[:100]} [dim](confidence {belief.get_current_confidence():.2f}, "
                f"updated {belief.updated_at.date().isoformat()}, retrievals {belief.retrieval_count})[/dim]"
            )
        console.print()

    if not yes:
        if not click.confirm(f"Archive {len(candidates)} belief(s)? (reversible - snapshots kept in the event log)"):
            click.echo("Cancelled. Nothing archived.")
            record_completed_health_archive(name, archived_count=0, cancelled=True)
            return

    changes = belief_store.archive_stale()
    loop_run = record_completed_health_archive(name, archived_count=len(changes))

    if json_output:
        click.echo(
            _json.dumps(
                {
                    "expert": name,
                    "count": len(changes),
                    "archived": [
                        {"belief_id": change.belief_id, "claim": change.old_claim, "reason": change.reason}
                        for change in changes
                    ],
                    "loop_run": loop_run.to_dict(),
                }
            )
        )
    else:
        print_success(f"Archived {len(changes)} belief(s). Restore any of them via the event-log snapshot.")


def archive_stale_with_scheduled_guard(
    name: str,
    *,
    profile_name: str,
    yes: bool,
    json_output: bool,
    scheduled: bool,
    jitter: float,
) -> None:
    """Run archival with the scheduled overlap guard when it can mutate."""
    if not (scheduled and yes):
        archive_stale_beliefs(name, yes=yes, json_output=json_output, scheduled=scheduled)
        return

    if jitter > 0:
        from deepr.experts.loop_lock import apply_startup_jitter

        apply_startup_jitter(profile_name, jitter)

    from deepr.experts.loop_lock import expert_verb_lock

    with expert_verb_lock(profile_name, "health-check") as acquired:
        if not acquired:
            from deepr.cli.commands.semantic.expert_health_schedule import emit_scheduled_archive_overlap

            emit_scheduled_archive_overlap(profile_name, json_output=json_output)
            return
        archive_stale_beliefs(name, yes=yes, json_output=json_output, scheduled=scheduled)


def canonical_profile_name(profile: Any, fallback: str) -> str:
    profile_name = getattr(profile, "name", None)
    return profile_name if isinstance(profile_name, str) and profile_name else fallback
