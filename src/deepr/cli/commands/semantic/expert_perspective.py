"""CLI: `deepr expert perspective` - ask an expert about something else entirely.

The normal consult path forbids this, correctly. Positions are ranked against
the question, dropped when they do not match, and an expert with no bearing
evidence reports `uncovered` rather than answering from adjacent material.
Answering outside your evidence while sounding evidenced is the failure the
whole system is built against.

This is a different mode, not a relaxation of that one. It never claims
coverage; it claims a frame. Ask an expert on Chinese writing about furniture
design and "what do your sources say about chairs" gets nothing, while "you
have spent years on a system where meaning is carried by stroke order and the
negative space inside a character - what does that make you notice here" gets
something worth having.

Two rules keep it honest, both enforced in ``cross_domain``: every observation
names the mapping it rests on, and every reading says where the analogy breaks.
An analogy presenting as evidence is fabrication with a citation attached.

$0. Local or prepaid plan, one model call.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import click

from deepr.cli.colors import console, print_header, print_key_value, print_success
from deepr.cli.commands.semantic.experts import expert
from deepr.cli.commands.semantic.study_backend import StudyBackendError, build_study_backend
from deepr.experts.cross_domain import (
    assemble_reading,
    build_cross_domain_prompt,
    frame_material,
    render_reading,
)
from deepr.experts.expert_layout import part_in
from deepr.experts.paths import canonical_expert_dir


def _load_profile(name: str) -> Any:
    from deepr.experts.profile import ExpertStore

    profile = ExpertStore().load(name)
    if not profile:
        click.echo(f"Error: Expert not found: {name}", err=True)
        sys.exit(2)
    return profile


def _build_context(expert_name: str, question: str) -> Any:
    """Assemble what this expert carries, without ranking it against the question.

    The question is passed through only because the context builder wants one.
    ``frame_material`` deliberately ignores the ranking: matching findings
    against a question from another subject surfaces whatever shares
    vocabulary with it, which is the least interesting thing an outside frame
    has to offer and the most likely to look like false relevance.
    """
    from deepr.experts.consult_context import build_consult_context, load_brief, load_study
    from deepr.experts.corpus_store import CorpusStore

    directory = canonical_expert_dir(expert_name)
    brief = load_brief(part_in(directory, "hold_current"))
    if brief is None:
        click.echo(
            f'Error: {expert_name} has no brief, so it holds no frame to lend. Run: deepr expert brief "{expert_name}"',
            err=True,
        )
        sys.exit(2)

    corpus: CorpusStore | None
    try:
        corpus = CorpusStore(expert_name)
    except Exception:
        corpus = None

    return build_consult_context(
        expert_name=expert_name,
        question=question,
        brief=brief,
        result=load_study(part_in(directory, "noticed")),
        corpus=corpus,
    )


def _parse_json(text: str) -> dict[str, Any]:
    """Recover the object from a model that would not stay out of prose."""
    candidate = (text or "").strip()
    start, end = candidate.find("{"), candidate.rfind("}")
    if start != -1 and end > start:
        candidate = candidate[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


@expert.command(name="perspective")
@click.argument("name")
@click.argument("question")
@click.option("--lens", "preferred_lens", default="", help="The reading of its own subject to lend")
@click.option("--local", is_flag=True, help="Use local Ollama ($0)")
@click.option("--plan", default=None, help="Prepaid plan backend id (e.g. claude)")
@click.option("--plan-model", default=None, help="Model for the plan backend")
@click.option("--model", default=None, help="Explicit local model")
@click.option("--out", type=click.Path(dir_okay=False, path_type=str), default=None, help="Write the reading here")
@click.option("--json", "as_json", is_flag=True, help="Emit the reading as JSON")
def expert_perspective(
    name: str,
    question: str,
    preferred_lens: str,
    local: bool,
    plan: str | None,
    plan_model: str | None,
    model: str | None,
    out: str | None,
    as_json: bool,
) -> None:
    """Ask NAME about QUESTION from outside its subject ($0).

    This is analogy and every rendering says so. NAME's sources say nothing
    about your question; what it lends is a way of looking, and the reading
    states where that way of looking breaks.

    Use `deepr expert consult` when you want the expert's evidence. Use this
    when you want its frame, which is the thing that travels.

    EXAMPLES:

      deepr expert perspective "Chinese Writing Systems" "how should I design flat-pack furniture"
      deepr expert perspective "Provenance and Belief Revision" "why do our migrations keep failing"
    """
    profile = _load_profile(name)
    context = _build_context(profile.name, question)
    material = frame_material(context)

    if not material.strip():
        click.echo(
            f"Error: {profile.name} is briefed but carries no patterns to lend. Run study, then brief.",
            err=True,
        )
        sys.exit(2)

    try:
        backend = build_study_backend(profile=profile, local=local, plan=plan, plan_model=plan_model, model=model)
    except StudyBackendError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(2)

    if not as_json:
        print_header(f"{profile.name}, on: {question}")
        print_key_value("Capacity", backend.cost_note)
        console.print("[dim]Analogy, not evidence. Check the mapping before relying on any of it.[/dim]")

    prompt = build_cross_domain_prompt(
        expert_name=profile.name,
        question=question,
        material=material,
        standpoint=context.orientation,
        preferred_lens=preferred_lens,
    )

    try:
        raw = asyncio.run(backend.completion(prompt))
    except Exception as exc:
        click.echo(f"Error: the model call failed: {type(exc).__name__}: {exc}", err=True)
        sys.exit(2)

    reading = assemble_reading(
        _parse_json(raw),
        expert_name=profile.name,
        question=question,
        standpoint=context.orientation,
        preferred_lens=preferred_lens,
    )

    # An empty reading is a real answer: a frame that does not reach the
    # subject should say so, because a forced analogy is worse than none. It
    # is not an error, so this exits 0 and renders the refusal.
    if as_json:
        click.echo(json.dumps(reading.to_dict(), indent=2))
    else:
        console.print()
        console.print(render_reading(reading))

    if out:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_reading(reading), encoding="utf-8")
        if not as_json:
            console.print()
            print_success(f"Written to {path}")
