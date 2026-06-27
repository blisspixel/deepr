"""Expert memory-card command."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from deepr.cli.colors import console, print_error, print_key_value, print_section_header, print_success
from deepr.cli.commands.semantic.experts import expert
from deepr.experts.memory_card import build_expert_memory_card, render_expert_memory_card, write_expert_memory_card
from deepr.experts.profile import ExpertStore


def _render_summary(payload: dict[str, Any]) -> None:
    print_section_header("Expert Memory Card")
    expert_info = payload["expert"]
    artifact = payload["artifact"]
    calibration = payload["calibration"]
    print_key_value("Expert", expert_info["name"])
    print_key_value("Domain", expert_info["domain"])
    print_key_value("Artifact", artifact["path"])
    print_key_value("Freshness", calibration["freshness_status"])
    print_key_value("Claims", str(payload["current_stance"]["belief_count"]))
    print_key_value("Open gaps", str(payload["current_stance"]["open_gap_count"]))

    console.print("\n[bold]Current stance[/bold]")
    console.print(f"  {payload['current_stance']['summary']}")

    if payload["current_goals"]:
        console.print("\n[bold]Current goals[/bold]")
        for goal in payload["current_goals"]:
            console.print(f"  - {goal}")

    console.print("\n[dim]Preview only. Re-run with --write to regenerate EXPERT.md.[/dim]")


@expert.command(name="memory-card")
@click.argument("name")
@click.option("--focus-limit", type=int, default=8, show_default=True, help="Maximum beliefs/gaps/events to include.")
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Optional markdown output path. Defaults to the expert's canonical EXPERT.md.",
)
@click.option("--write", "write_markdown", is_flag=True, help="Atomically write the generated markdown card.")
@click.option("--markdown", "markdown_output", is_flag=True, help="Emit generated markdown to stdout.")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def expert_memory_card(
    name: str,
    focus_limit: int,
    output: Path | None,
    write_markdown: bool,
    markdown_output: bool,
    json_output: bool,
) -> None:
    """Show or regenerate a wiki-style EXPERT.md derived from expert state."""
    store = ExpertStore()
    profile = store.load(name)
    if profile is None:
        print_error(f"Expert '{name}' not found")
        raise click.Abort()

    manifest = profile.get_manifest()
    if write_markdown:
        artifact = write_expert_memory_card(
            profile,
            manifest=manifest,
            focus_limit=focus_limit,
            output_path=output,
        )
        payload = dict(artifact.payload)
        payload["artifact"] = {**payload["artifact"], "written_path": str(artifact.path)}
        if json_output:
            click.echo(json.dumps(payload, indent=2, default=str))
            return
        if markdown_output:
            click.echo(artifact.markdown, nl=False)
            return
        print_success(f"Wrote expert memory card: {artifact.path}")
        return

    payload = build_expert_memory_card(profile, manifest=manifest, focus_limit=focus_limit)
    if json_output:
        click.echo(json.dumps(payload, indent=2, default=str))
        return
    if markdown_output:
        click.echo(render_expert_memory_card(payload), nl=False)
        return
    _render_summary(payload)
