"""One attended command to form a local expert's research foundation."""

from __future__ import annotations

import asyncio

import click

from deepr.cli.colors import console
from deepr.cli.commands.semantic.experts import expert
from deepr.cli.commands.semantic.local_expert import local_formation_options
from deepr.cli.commands.semantic.study_backend import build_study_backend
from deepr.cli.companion import companion_work, print_companion
from deepr.experts.formation import FormationLimits, form_expert, read_formation_state
from deepr.experts.profile import ExpertStore


def build_local_expert(
    profile,
    *,
    model: str | None = None,
    discover: bool = True,
    limits: FormationLimits | None = None,
    refresh_sources: bool = False,
    fresh_default: bool = False,
):
    limits = limits or FormationLimits()
    limits.validate()
    previous = read_formation_state(profile.name) or {}
    if previous.get("model") is not None and not isinstance(previous["model"], str):
        raise ValueError("Previous formation model identity is malformed; inspect its retained operation record")
    recorded = profile.model if profile.provider == "local" and not fresh_default else None
    selected = model or previous.get("model") or recorded
    selected = selected if selected and selected != "ollama" else None
    with companion_work("Build research foundation", console=console) as status:
        backend = build_study_backend(profile=profile, local=True, model=selected)
        click.echo("Building research, perspective, and linked knowledge with owned local capacity ($0 API cost).")
        result = asyncio.run(
            form_expert(
                profile,
                backend,
                limits=limits,
                discover=discover,
                refresh_sources=refresh_sources,
                on_progress=lambda note: status.update(note) if status else click.echo(f"  {note}"),
            )
        )
    click.echo(f"Formation: {result['status']}")
    if result["status"] != "research_complete":
        print_companion("error", "Formation incomplete", console=console)
        raise click.ClickException(f"{result['progress']}. Completed evidence was retained for inspection.")
    click.echo(f"Knowledge: {result['knowledge_index']}")
    click.echo("Research foundation built. Practical advice and currentness still require review.")
    return result


@expert.command(name="build")
@click.argument("name")
@click.option("--local-model", default=None, help="Installed local model for research and study")
@click.option("--no-discovery", is_flag=True, help="Study retained sources without new web acquisition")
@click.option(
    "--refresh-sources", is_flag=True, help="Explicitly reacquire sources instead of reusing verified acquisition"
)
@local_formation_options
def expert_build(
    name: str,
    local_model: str | None,
    no_discovery: bool,
    refresh_sources: bool,
    max_minutes: int,
    max_corpus_chars: int,
):
    """Research and form an existing untrained local profile at $0 API cost.

    Uses bounded free search, local study, a reasoned brief, graph, and Markdown.
    Existing formed experts require explicit maintenance instead of replacement.
    """
    profile = ExpertStore().load(name)
    if profile is None:
        raise click.ClickException(f"Expert not found: {name}")
    try:
        if refresh_sources and no_discovery:
            raise ValueError("--refresh-sources and --no-discovery cannot be combined")
        limits = FormationLimits(max_elapsed_seconds=max_minutes * 60, max_corpus_chars=max_corpus_chars)
        build_local_expert(
            profile, model=local_model, discover=not no_discovery, limits=limits, refresh_sources=refresh_sources
        )
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
