"""One attended command to form a local expert's research foundation."""

from __future__ import annotations

import asyncio

import click

from deepr.cli.commands.semantic.experts import expert
from deepr.cli.commands.semantic.study_backend import build_study_backend
from deepr.experts.formation import FormationLimits, form_expert
from deepr.experts.profile import ExpertStore


def build_local_expert(
    profile, *, model: str | None = None, discover: bool = True, limits: FormationLimits | None = None
):
    backend = build_study_backend(profile=profile, local=True, model=model)
    click.echo("Building research, perspective, and linked knowledge with owned local capacity ($0 API cost).")
    result = asyncio.run(
        form_expert(
            profile, backend, limits=limits, discover=discover, on_progress=lambda note: click.echo(f"  {note}")
        )
    )
    click.echo(f"Formation: {result['status']}")
    if result["status"] != "research_complete":
        raise click.ClickException(f"{result['progress']}. Completed evidence was retained for inspection.")
    click.echo(f"Knowledge: {result['knowledge_index']}")
    click.echo("Research foundation built. Practical advice and currentness still require review.")
    return result


@expert.command(name="build")
@click.argument("name")
@click.option("--local-model", default=None, help="Installed local model for research and study")
@click.option("--no-discovery", is_flag=True, help="Study retained sources without new web acquisition")
def expert_build(name: str, local_model: str | None, no_discovery: bool):
    """Research and form an existing untrained local profile at $0 API cost.

    Uses bounded free search, local study, a reasoned brief, graph, and Markdown.
    Existing formed experts require explicit maintenance instead of replacement.
    """
    profile = ExpertStore().load(name)
    if profile is None:
        raise click.ClickException(f"Expert not found: {name}")
    try:
        build_local_expert(profile, model=local_model, discover=not no_discovery)
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
