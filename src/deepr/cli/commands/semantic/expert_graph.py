"""CLI: `deepr expert graph` - write down the chain the expert already holds.

A finding records the sources its anchors were found in. A position records the
findings it rests on. That is a two-hop path from a claim to a passage, and it
has been kept as three flat lists in two files since the study pass existed, so
the question it exists to answer had to be recomputed by hand every time.

This materialises it. No model call and no network: every edge is copied from a
field already on disk, which is why it can be rebuilt at any time and why it is
free.

Written to `<expert>/graph/evidence.json`, beside the concept graph the chat
path builds. They are different graphs answering different questions - that one
joins phrases by co-occurrence for retrieval, this one joins claims to passages
for provenance - and neither replaces the other.

$0.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click

from deepr.cli.colors import console, print_header, print_key_value, print_success, print_warning
from deepr.cli.commands.semantic.experts import expert
from deepr.experts.evidence_graph import build_graph, render_graph
from deepr.experts.expert_layout import became_path, evidence_graph_path, part_in
from deepr.experts.paths import canonical_expert_dir
from deepr.experts.perspective_graph import render_perspective
from deepr.utils.atomic_io import atomic_write_json


def canonical_graph_path(expert_name: str) -> Path:
    """Where the evidence graph lives, and where anything reading one looks."""
    return evidence_graph_path(expert_name)


def canonical_perspective_path(expert_name: str) -> Path:
    """Where the expert's account of itself lives."""
    return became_path(expert_name)


def _build_perspective(expert_name: str, *, at: str) -> Any:
    """Assemble the biography from what the expert wrote about itself.

    Separate from the evidence graph on purpose. That one answers "why do you
    think that" and is a fact structure. This one answers "who are you and
    what moved you", and its nodes have no truth value - a commitment about
    conduct is not a claim about the world, and it is still part of who the
    expert is.
    """
    from deepr.experts.expert_profile_card import ExpertProfile
    from deepr.experts.perspective_graph import build_perspective_graph
    from deepr.experts.viva import VivaResult

    directory = canonical_expert_dir(expert_name)

    profile = None
    try:
        profile = ExpertProfile.from_dict(json.loads(part_in(directory, "self").read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        pass

    viva = None
    try:
        viva = VivaResult(
            expert_name=expert_name,
            positions_that_moved=list(
                json.loads(part_in(directory, "met_examination").read_text(encoding="utf-8")).get(
                    "positions_that_moved"
                )
                or []
            ),
        )
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        pass

    return build_perspective_graph(expert_name=expert_name, profile=profile, viva=viva, at=at)


def _load_profile(name: str) -> Any:
    from deepr.experts.profile import ExpertStore

    profile = ExpertStore().load(name)
    if not profile:
        click.echo(f"Error: Expert not found: {name}", err=True)
        sys.exit(2)
    return profile


def _corpus_entries(expert_name: str) -> list[Any]:
    """The retained sources, so an edge can only point at a real passage."""
    try:
        from deepr.experts.corpus_store import CorpusStore

        return list(CorpusStore(expert_name).active_entries())
    except Exception:
        return []


def _render_human(graph: Any, *, path: Path) -> None:
    stats = graph.stats()
    print_key_value(
        "Graph",
        f"{stats['sources']} source(s), {stats['findings']} finding(s), "
        f"{stats['positions']} position(s), {stats['edges']} edge(s)",
    )

    if not stats["is_formed"]:
        print_warning(
            "No position reaches a source through a finding, so this is a pile of nodes "
            "rather than a graph. Run study and brief first."
        )

    if graph.unsupported_positions:
        console.print("\n[red]Positions that reach no source[/red]")
        for node in graph.unsupported_positions:
            console.print(f"  - {node.label}")
        console.print("[dim]A claim whose bibliography cites empty pages. Re-brief or re-study.[/dim]")

    if graph.unused_findings:
        console.print(f"\n[yellow]{len(graph.unused_findings)} grounded finding(s) support no position[/yellow]")
        console.print("[dim]Either the brief missed something or this part of the corpus was read for nothing.[/dim]")

    if load_bearing := graph.load_bearing_sources():
        console.print("\n[cyan]What the claims actually rest on[/cyan]")
        for label, count in load_bearing:
            console.print(f"  {count:>3} position(s)  {label}")

    console.print()
    print_success(f"Written to {path}")


def _render_perspective_summary(perspective: Any, *, path: Path) -> None:
    """Who the expert is, as distinct from what it can prove."""
    console.print()
    if perspective.chosen_name:
        print_key_value("Calls itself", perspective.chosen_name)

    stats = perspective.stats()
    print_key_value(
        "Perspective",
        f"{stats['standpoints']} standpoint(s), {stats['shifts']} recorded change(s) of mind, "
        f"{stats['pursuits']} open pursuit(s)",
    )

    if not perspective.has_a_history:
        print_warning(
            "Never recorded changing its mind. It may have read a great deal; nothing it read "
            "has moved it, which is the state a new expert is already in."
        )
    else:
        console.print("\n[bright_yellow]What moved it[/bright_yellow]")
        for shift in perspective.shifts[:5]:
            console.print(f"  - {shift.text}")

    print_success(f"Written to {path}")


@expert.command(name="graph")
@click.argument("name")
@click.option("--out", type=click.Path(dir_okay=False, path_type=str), default=None, help="Write the graph JSON here")
@click.option("--markdown", "write_markdown", is_flag=True, help="Also write the readable summary")
@click.option("--json", "as_json", is_flag=True, help="Emit the graph JSON to stdout")
def expert_graph(name: str, out: str | None, write_markdown: bool, as_json: bool) -> None:
    """Build NAME's evidence graph from what is already on disk ($0, no model).

    Nodes are sources, findings and positions; edges are the support each one
    recorded. Nothing is inferred, so this is a change of storage rather than a
    new claim and it can be rebuilt whenever the study or brief changes.

    What it makes cheap: which positions reach no source at all, which grounded
    findings nothing rests on, and which passages the claims actually trace
    back to. All three are expensive to ask across two flat files.

    EXAMPLES:

      deepr expert graph "My Expert"
      deepr expert graph "My Expert" --markdown
    """
    from deepr.experts.consult_context import load_brief, load_study

    profile = _load_profile(name)
    directory = canonical_expert_dir(profile.name)
    study = load_study(part_in(directory, "noticed"))
    brief = load_brief(part_in(directory, "hold_current"))

    if study is None and brief is None:
        click.echo(
            f"Error: {profile.name} has neither a study nor a brief, so there is no chain to record. "
            f'Run: deepr expert study "{profile.name}"',
            err=True,
        )
        sys.exit(2)

    built_at = datetime.now(UTC).isoformat()
    graph = build_graph(
        expert_name=profile.name,
        study=study,
        brief=brief,
        corpus_entries=_corpus_entries(profile.name),
        at=built_at,
    )

    path = Path(out) if out else canonical_graph_path(profile.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, graph.to_dict(), fsync=True)

    # The biography, beside the evidence. Two graphs answering two questions:
    # "why do you think that" and "who are you and what moved you".
    perspective = _build_perspective(profile.name, at=built_at)
    perspective_path = canonical_perspective_path(profile.name)
    atomic_write_json(perspective_path, perspective.to_dict(), fsync=True)

    if write_markdown:
        path.with_suffix(".md").write_text(render_graph(graph), encoding="utf-8")
        perspective_path.with_suffix(".md").write_text(render_perspective(perspective), encoding="utf-8")

    if as_json:
        click.echo(json.dumps(graph.to_dict(), indent=2))
    else:
        print_header(f"Graphs: {profile.name}")
        _render_human(graph, path=path)
        _render_perspective_summary(perspective, path=perspective_path)
