"""Expert self-model command."""

from __future__ import annotations

import json
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
