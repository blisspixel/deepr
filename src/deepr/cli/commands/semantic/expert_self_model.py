"""Expert self-model command."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from deepr.cli.colors import console, print_error, print_key_value, print_section_header
from deepr.cli.commands.semantic.experts import expert
from deepr.experts.profile import ExpertStore
from deepr.experts.self_model import build_expert_self_model


def _render(payload: dict[str, Any]) -> None:
    print_section_header("Expert Self-Model")
    expert_info = payload["expert"]
    print_key_value("Expert", expert_info["name"])
    print_key_value("Domain", expert_info["domain"] or "(unspecified)")
    print_key_value("Freshness", payload["calibration"]["freshness_status"])
    print_key_value("Claims", str(payload["capabilities"]["claim_count"]))
    print_key_value("Open gaps", str(payload["capabilities"]["open_gap_count"]))

    if payload["current_goals"]:
        console.print("\n[bold]Current goals[/bold]")
        for goal in payload["current_goals"]:
            console.print(f"  - {goal}")

    if payload["unresolved_risks"]:
        console.print("\n[bold]Unresolved risks[/bold]")
        for risk in payload["unresolved_risks"]:
            console.print(f"  - {risk}")


@expert.command(name="self-model")
@click.argument("name")
@click.option("--focus-limit", type=int, default=5, show_default=True, help="Maximum beliefs/gaps in focus packet.")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def expert_self_model(name: str, focus_limit: int, json_output: bool) -> None:
    """Show a read-only self-model derived from an expert manifest."""
    store = ExpertStore()
    profile = store.load(name)
    if profile is None:
        print_error(f"Expert '{name}' not found")
        raise click.Abort()

    payload = build_expert_self_model(profile, profile.get_manifest(), focus_limit=focus_limit)
    if json_output:
        click.echo(json.dumps(payload, indent=2, default=str))
        return
    _render(payload)


def _render_monitor(payload: dict[str, Any]) -> None:
    print_section_header("Metacognitive Monitor")
    print_key_value("Expert", payload["expert_name"])
    print_key_value("Proposals", str(payload["proposal_count"]))
    signals = payload["signals"]
    print_key_value("Failed loops", str(signals["failed_loop_count"]))
    print_key_value("Consult candidates", str(signals["consult_trace_candidate_count"]))
    proposals = list(payload.get("proposals", []) or [])
    if not proposals:
        console.print("[dim]No monitor proposals found.[/dim]")
        return
    for proposal in proposals[:10]:
        console.print(f"\n[bold]{proposal['title']}[/bold]")
        console.print(f"  {proposal['proposal_type']} -> {proposal['target']}")
        console.print(f"  {proposal['rationale']}")
        console.print(f"  [dim]{proposal['recommended_command']}[/dim]")


@expert.command(name="monitor")
@click.argument("name")
@click.option("--limit", type=int, default=20, show_default=True, help="Recent loop runs and traces to inspect.")
@click.option("--max-proposals", type=int, default=20, show_default=True, help="Maximum proposals to emit.")
@click.option(
    "--trace-path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Optional local consult trace JSONL path.",
)
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def expert_monitor(
    name: str,
    limit: int,
    max_proposals: int,
    trace_path: Path | None,
    json_output: bool,
) -> None:
    """Emit read-only metacognitive proposals from measured expert evidence."""
    from deepr.experts.loop_runs import ExpertLoopRunStore
    from deepr.experts.metacognitive_monitor import (
        build_consult_trace_candidates_for_expert,
        build_metacognitive_monitor_report,
    )

    store = ExpertStore()
    profile = store.load(name)
    if profile is None:
        print_error(f"Expert '{name}' not found")
        raise click.Abort()

    scan_limit = max(0, limit)
    proposal_limit = max(0, max_proposals)
    loop_runs = [] if scan_limit == 0 else ExpertLoopRunStore(profile.name).list_runs(limit=scan_limit)
    candidates = build_consult_trace_candidates_for_expert(
        profile.name,
        path=trace_path,
        limit=scan_limit,
        max_candidates=proposal_limit,
    )
    payload = build_metacognitive_monitor_report(
        profile,
        loop_runs=loop_runs,
        consult_trace_candidates=candidates,
        max_proposals=proposal_limit,
    )
    if json_output:
        click.echo(json.dumps(payload, indent=2, default=str))
        return
    _render_monitor(payload)
