"""Inspectable linked knowledge derived from an expert's retained research."""

from __future__ import annotations

import click

from deepr.cli.commands.semantic.experts import expert
from deepr.experts.consult_context import load_brief, load_study
from deepr.experts.corpus_store import CorpusStore
from deepr.experts.expert_layout import part_in
from deepr.experts.knowledge_wiki import write_knowledge_view
from deepr.experts.paths import canonical_expert_dir
from deepr.experts.position_ledger import load_ledger
from deepr.experts.profile import ExpertStore


def render_expert_knowledge(name: str):
    """Regenerate an existing expert's view without research or inference."""
    directory = canonical_expert_dir(name)
    study = load_study(part_in(directory, "noticed"))
    brief = load_brief(part_in(directory, "hold_current"))
    if study is None or brief is None:
        raise ValueError("A readable study and brief are required; a profile alone has no knowledge to project.")
    history = load_ledger(part_in(directory, "hold_history"), expert_name=name)
    return write_knowledge_view(
        directory, study=study, brief=brief, entries=CorpusStore(name).active_entries(), history=history.to_dict()
    )


@expert.command(name="knowledge")
@click.argument("name")
def expert_knowledge(name: str) -> None:
    """Build linked Markdown pages and their evidence graph ($0, no model).

    View concepts, research, reasoned positions, sources, and recorded history.
    Generated pages preserve earlier views and do not certify advice quality.
    """
    profile = ExpertStore().load(name)
    if profile is None:
        raise click.ClickException(f"Expert not found: {name}")
    try:
        path = render_expert_knowledge(profile.name)
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Linked knowledge: {path}")
