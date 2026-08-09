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
from deepr.experts.paths import canonical_expert_dir


def canonical_graph_path(expert_name: str) -> Path:
    """Where the evidence graph lives, and where anything reading one looks."""
    return canonical_expert_dir(expert_name) / "graph" / "evidence.json"


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
    study = load_study(directory / "study.json")
    brief = load_brief(directory / "brief.json")

    if study is None and brief is None:
        click.echo(
            f"Error: {profile.name} has neither a study nor a brief, so there is no chain to record. "
            f'Run: deepr expert study "{profile.name}"',
            err=True,
        )
        sys.exit(2)

    graph = build_graph(
        expert_name=profile.name,
        study=study,
        brief=brief,
        corpus_entries=_corpus_entries(profile.name),
        at=datetime.now(UTC).isoformat(),
    )

    path = Path(out) if out else canonical_graph_path(profile.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(graph.to_dict(), indent=2), encoding="utf-8")

    if write_markdown:
        path.with_suffix(".md").write_text(render_graph(graph), encoding="utf-8")

    if as_json:
        click.echo(json.dumps(graph.to_dict(), indent=2))
    else:
        print_header(f"Evidence graph: {profile.name}")
        _render_human(graph, path=path)
