"""CLI: `deepr expert viva` - examine an expert, where nobody has the answer key.

The evaluation problem this solves: how do you find out whether an expert
understands its subject when there is no ground truth, and nobody available
already knows? A doctoral viva answers it, and the reason it works is the part
that looks like a defect - the examiners frequently do not know the answer to
what they are asking. They probe rather than mark, and both sides come out
knowing more than they went in with.

The outputs are a transcript, a reading list, and occasionally a position that
did not survive a good question. Not a score: compressing this to a letter
would discard the part worth having, and `deepr expert health` already covers
the letter-shaped question.

$0. Local or prepaid plan, the same capacity story as `expert study`, and no
route to a metered API from here.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import click

from deepr.cli.colors import console, print_header, print_key_value, print_success, print_warning
from deepr.cli.commands.semantic.experts import expert
from deepr.cli.commands.semantic.study_backend import StudyBackendError, build_study_backend
from deepr.experts.paths import canonical_expert_dir
from deepr.experts.viva import VivaResult, render_viva
from deepr.experts.viva_session import DEFAULT_PANEL, Examiner, run_viva
from deepr.utils.atomic_io import atomic_write_json

_MAX_BRIEF_CHARS = 60_000
"""What an examiner is shown. A brief is small; this is a runaway guard, not a
budget, and a brief that hits it is a brief with something wrong with it."""


def canonical_viva_path(expert_name: str) -> Path:
    """Where an examination is written, and where anything reading one looks."""
    return canonical_expert_dir(expert_name) / "viva.json"


def _load_profile(name: str) -> Any:
    from deepr.experts.profile import ExpertStore

    profile = ExpertStore().load(name)
    if not profile:
        click.echo(f"Error: Expert not found: {name}", err=True)
        sys.exit(2)
    return profile


def _load_brief_text(expert_name: str) -> str:
    """Render the brief the candidate will be examined on.

    Exits rather than examining an unbriefed expert. A viva probes whether the
    thinking under a position is load-bearing; with no positions there is
    nothing to probe, and the examination would be three model calls producing
    a document that says so.
    """
    from deepr.experts.brief import render_brief
    from deepr.experts.consult_context import load_brief

    brief = load_brief(canonical_expert_dir(expert_name) / "brief.json")
    if brief is None:
        click.echo(
            f"Error: {expert_name} has no brief, so it holds no positions to examine. "
            f'Run: deepr expert brief "{expert_name}"',
            err=True,
        )
        sys.exit(2)
    return render_brief(brief)[:_MAX_BRIEF_CHARS]


def _panel_from_experts(names: tuple[str, ...]) -> list[Examiner]:
    """Borrow other experts as examiners, each standing where it actually stands.

    Better than the default panel, because a frame built against real material
    notices things a frame described in one sentence does not. An examiner with
    no standpoint of its own is dropped rather than sent in with an empty one:
    it would revert to asking the subject's own obvious questions, which the
    candidate has already answered in its brief.
    """
    from deepr.experts.consult_context import load_brief

    panel: list[Examiner] = []
    for name in names:
        brief = load_brief(canonical_expert_dir(name) / "brief.json")
        if brief is None:
            print_warning(f"Skipping examiner {name}: no brief, so it has no standpoint to ask from.")
            continue
        orientation = (brief.orientation or "").strip()
        if not orientation:
            print_warning(f"Skipping examiner {name}: briefed but holds no orientation of its own.")
            continue
        panel.append(
            Examiner(name=name, frame=f'your work on "{name}", where you read the subject like this: {orientation}')
        )
    return panel


def _route_gaps(result: VivaResult) -> list[dict[str, Any]]:
    """Say which instrument would fill each gap, and what it would cost.

    A reading list nobody can act on is a document. This does not dispatch
    anything - it runs the same advisory router `expert gap-routes` uses, so
    the transcript carries a costed next step per gap instead of a wish.

    Router failure is reported and does not fail the examination: the
    transcript is already written and is the expensive part.
    """
    if not result.gaps:
        return []
    try:
        from deepr.core.contracts import Gap
        from deepr.experts.gap_router import GapRouter
        from deepr.experts.gap_scorer import score_gap

        router = GapRouter()
        return [router.route_gap(score_gap(Gap.create(**payload))).to_dict() for payload in result.as_gaps()]
    except Exception as exc:
        print_warning(f"Could not route {len(result.gaps)} gap(s): {exc}")
        return []


def _render_human(result: VivaResult, *, path: Path, routes: list[dict[str, Any]]) -> None:
    console.print()
    print_key_value("Examination", result.summary())

    if result.positions_that_moved:
        console.print("\n[bright_yellow]Moved under questioning[/bright_yellow]")
        for item in result.positions_that_moved:
            console.print(f"  - {item}")

    if result.gaps:
        console.print("\n[cyan]Answerable, and unanswered[/cyan]")
        by_topic = {r.get("topic", ""): r for r in routes}
        for exchange, item in zip(result.gaps, result.reading_queue(), strict=False):
            console.print(f"  - {item}")
            route = by_topic.get(f"Viva gap ({result.expert_name}): {exchange.would_resolve_it}")
            if route:
                cost = route.get("estimated_cost", 0.0)
                console.print(f"    [dim]{route.get('instrument')}, about ${cost:.2f}[/dim]")

    if result.frontier:
        console.print("\n[dim]Where the field itself has not settled[/dim]")
        for exchange in result.frontier:
            console.print(f"  [dim]- {exchange.question}[/dim]")

    console.print()
    print_success(f"Written to {path}")


@expert.command(name="viva")
@click.argument("name")
@click.option(
    "--examiner",
    "examiners",
    multiple=True,
    help="Another expert to examine this one (repeatable). Defaults to a three-standpoint panel.",
)
@click.option("--questions", default=4, show_default=True, help="Questions per examiner")
@click.option("--local", is_flag=True, help="Use local Ollama ($0)")
@click.option("--plan", default=None, help="Prepaid plan backend id (e.g. claude)")
@click.option("--plan-model", default=None, help="Model for the plan backend")
@click.option("--model", default=None, help="Explicit local model")
@click.option("--out", type=click.Path(dir_okay=False, path_type=str), default=None, help="Write the viva JSON here")
@click.option("--markdown", "write_markdown", is_flag=True, help="Also write the transcript as Markdown")
@click.option("--json", "as_json", is_flag=True, help="Emit the viva JSON to stdout")
def expert_viva(
    name: str,
    examiners: tuple[str, ...],
    questions: int,
    local: bool,
    plan: str | None,
    plan_model: str | None,
    model: str | None,
    out: str | None,
    write_markdown: bool,
    as_json: bool,
) -> None:
    """Examine NAME by questioning, and find out what it cannot answer ($0).

    Examiners probe from their own standpoint rather than as second
    specialists, because a frame built elsewhere notices what an insider has
    stopped seeing. They are not marking against an answer key and are not
    expected to know the subject.

    What comes out is a transcript, the questions it could not answer that
    material exists to answer, the ones nobody can answer, and any position the
    expert withdrew under questioning. There is no grade - `deepr expert
    health` is the letter-shaped question, and it measures something else.

    EXAMPLES:

      deepr expert viva "My Expert"
      deepr expert viva "My Expert" --examiner "Provenance and Belief Revision"
      deepr expert viva "My Expert" --plan claude --markdown
    """
    profile = _load_profile(name)
    brief_text = _load_brief_text(profile.name)

    panel = _panel_from_experts(examiners) if examiners else list(DEFAULT_PANEL)
    if not panel:
        click.echo("Error: no usable examiners. Every named expert lacked a brief to ask from.", err=True)
        sys.exit(2)
    panel = [Examiner(name=e.name, frame=e.frame, questions=questions) for e in panel]

    try:
        backend = build_study_backend(profile=profile, local=local, plan=plan, plan_model=plan_model, model=model)
    except StudyBackendError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(2)

    if not as_json:
        print_header(f"Viva: {profile.name}")
        print_key_value("Capacity", backend.cost_note)
        print_key_value("Panel", ", ".join(e.name for e in panel))
        console.print("[dim]The examiners do not hold the answers either. That is the format.[/dim]")

    result = asyncio.run(
        run_viva(
            expert_name=profile.name,
            subject=profile.name,
            brief=brief_text,
            examiners=panel,
            completion=backend.completion,
        )
    )

    # Refuse before writing. A failed panel used to overwrite a good
    # transcript with an empty one, so a backend hiccup destroyed an
    # examination that had already cost quota and several minutes.
    if not result.exchanges:
        why = f" Every call failed with: {result.failures[0]}" if result.failures else ""
        click.echo(
            "Error: no examiner produced a question, so nothing was examined."
            f"{why} Any previous transcript has been left alone.",
            err=True,
        )
        sys.exit(2)

    if result.failures:
        print_warning(f"{len(result.failures)} call(s) failed during the examination: {result.failures[0]}")

    payload = result.to_dict()
    payload["gap_routes"] = _route_gaps(result)

    path = Path(out) if out else canonical_viva_path(profile.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, payload, fsync=True)

    if write_markdown:
        markdown_path = path.with_suffix(".md")
        markdown_path.write_text(render_viva(result), encoding="utf-8")

    if as_json:
        click.echo(json.dumps(payload, indent=2))
    else:
        _render_human(result, path=path, routes=payload["gap_routes"])
