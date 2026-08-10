"""CLI: `deepr expert practice` - what this expert is doing to stay expert.

A specialist does not stay a specialist by having read a lot once. They keep a
practice: questions they are actively chasing, sources they follow because
those sources keep being worth reading, and areas they are deepening as
distinct from areas they merely track. Next month's reading differs from last
month's because of that, and it is what turns elapsed time into expertise.

The work is split deliberately, and the split is the design:

- **Measured, never asked.** Which sources the expert follows comes from the
  evidence graph - the publishers its own positions actually rest on. Letting a
  model rank them would reintroduce exactly the guessing that measuring them
  replaced: an expert would follow what it finds appealing rather than what
  carries its claims.
- **Decided by the expert.** Which questions are now answered, which turned out
  to be the wrong question, what it wants to know next, and where its attention
  should go. Those are judgements, and a deterministic rule pretending to make
  them would be the brittle-regex failure this project keeps correcting.

$0. One model call on local or prepaid plan.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click

from deepr.cli.colors import console, print_header, print_key_value, print_success, print_warning
from deepr.cli.commands.semantic.experts import expert
from deepr.cli.commands.semantic.study_backend import StudyBackendError, build_study_backend
from deepr.experts.paths import canonical_expert_dir
from deepr.experts.research_practice import (
    ResearchPractice,
    apply_practice_update,
    build_practice_prompt,
    open_pursuits,
    render_practice,
    update_watches,
)
from deepr.utils.atomic_io import atomic_write_json

_MAX_MATERIAL_CHARS = 40_000


def canonical_practice_path(expert_name: str) -> Path:
    """Where the practice lives, and where acquisition should read it."""
    return canonical_expert_dir(expert_name) / "practice.json"


def _load_profile(name: str) -> Any:
    from deepr.experts.profile import ExpertStore

    profile = ExpertStore().load(name)
    if not profile:
        click.echo(f"Error: Expert not found: {name}", err=True)
        sys.exit(2)
    return profile


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _load_practice(expert_name: str) -> ResearchPractice:
    stored = _read_json(canonical_practice_path(expert_name))
    if not stored:
        return ResearchPractice(expert_name=expert_name)
    return ResearchPractice.from_dict(stored)


def _seed_from_artifacts(practice: ResearchPractice, expert_name: str, *, at: str) -> None:
    """Fold in the questions and sources the expert has already produced.

    Both halves already exist and neither fed anything: a viva names exactly
    what the expert could not answer but material exists to answer, and the
    evidence graph knows which publishers the positions rest on. Until now the
    first was a list in a file and the second was recomputed for a report.
    """
    directory = canonical_expert_dir(expert_name)

    viva = _read_json(directory / "viva.json")
    open_pursuits(
        practice,
        [str(q) for q in (viva.get("reading_queue") or [])],
        origin="viva",
        at=at,
        why="an examiner found this answerable and I could not answer it",
    )

    profile = _read_json(directory / "profile_card.json")
    open_pursuits(
        practice,
        [str(q) for q in (profile.get("open_questions") or [])],
        origin="profile",
        at=at,
        why="I named this as something I am still working on",
    )

    graph = _read_json(directory / "graph" / "evidence.json")
    load_bearing = [
        (str(row.get("source") or ""), int(row.get("positions") or 0))
        for row in (graph.get("load_bearing_sources") or [])
        if isinstance(row, dict)
    ]
    update_watches(practice, load_bearing, at=at)


def _material(expert_name: str) -> str:
    """What the expert has read since, for reviewing its own questions against."""
    from deepr.experts.brief import render_brief
    from deepr.experts.consult_context import load_brief

    brief = load_brief(canonical_expert_dir(expert_name) / "brief.json")
    if brief is None:
        return ""
    return render_brief(brief)[:_MAX_MATERIAL_CHARS]


def _parse_json(text: str) -> dict[str, Any]:
    candidate = (text or "").strip()
    start, end = candidate.find("{"), candidate.rfind("}")
    if start != -1 and end > start:
        candidate = candidate[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _render(practice: ResearchPractice, changed: dict[str, int], *, path: Path) -> None:
    stats = practice.stats()
    console.print()
    print_key_value(
        "Practice",
        f"{stats['live_pursuits']} live pursuit(s), {stats['watches']} source(s) followed, "
        f"{stats['deepening']} area(s) being deepened",
    )
    if any(changed.values()):
        print_key_value(
            "This round",
            f"{changed['answered']} answered, {changed['abandoned']} abandoned, {changed['opened']} opened",
        )

    if not practice.is_practising:
        print_warning(
            "No live questions, or nowhere it is following. It is not keeping up with anything - "
            "it is waiting to be re-researched."
        )

    if reading := practice.next_reading():
        console.print("\n[cyan]What it would read next[/cyan]")
        for item in reading:
            console.print(f"  - {item}")

    console.print()
    print_success(f"Written to {path}")


@expert.command(name="practice")
@click.option("--local", is_flag=True, help="Use local Ollama ($0)")
@click.option("--plan", default=None, help="Prepaid plan backend id (e.g. claude)")
@click.option("--plan-model", default=None, help="Model for the plan backend")
@click.option("--model", default=None, help="Explicit local model")
@click.option("--show", is_flag=True, help="Show the current practice without updating it ($0, no model)")
@click.option("--markdown", "write_markdown", is_flag=True, help="Also write the readable summary")
@click.option("--json", "as_json", is_flag=True, help="Emit the practice JSON")
@click.argument("name")
def expert_practice(
    name: str,
    local: bool,
    plan: str | None,
    plan_model: str | None,
    model: str | None,
    show: bool,
    write_markdown: bool,
    as_json: bool,
) -> None:
    """Update what NAME is chasing, following, and paying attention to ($0).

    Sources it follows are measured from which publishers its positions rest
    on, so they cannot be argued for. Everything else is the expert's own
    call: which questions its recent reading has answered, which turned out to
    be the wrong question, what it wants to know next, and where to go deep.

    The result is what an acquisition pass should read next - a question is a
    better search than a topic string, and this is where the questions live.

    EXAMPLES:

      deepr expert practice "My Expert" --show
      deepr expert practice "My Expert" --plan claude --markdown
    """
    profile = _load_profile(name)
    at = datetime.now(UTC).isoformat()

    practice = _load_practice(profile.name)
    _seed_from_artifacts(practice, profile.name, at=at)
    changed = {"answered": 0, "abandoned": 0, "opened": 0}

    if not show:
        try:
            backend = build_study_backend(profile=profile, local=local, plan=plan, plan_model=plan_model, model=model)
        except StudyBackendError as exc:
            click.echo(f"Error: {exc}", err=True)
            sys.exit(2)

        if not as_json:
            print_header(f"Practice: {profile.name}")
            print_key_value("Capacity", backend.cost_note)

        card = _read_json(canonical_expert_dir(profile.name) / "profile_card.json")
        prompt = build_practice_prompt(
            expert_name=str(card.get("chosen_name") or profile.name),
            standpoint=str(card.get("standpoint") or ""),
            practice=practice,
            material=_material(profile.name),
        )
        try:
            raw = asyncio.run(backend.completion(prompt))
        except Exception as exc:
            click.echo(f"Error: the model call failed: {type(exc).__name__}: {exc}", err=True)
            sys.exit(2)

        changed = apply_practice_update(practice, _parse_json(raw), at=at)
    else:
        practice.updated_at = at

    path = canonical_practice_path(profile.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, practice.to_dict(), fsync=True)

    if write_markdown:
        path.with_suffix(".md").write_text(render_practice(practice), encoding="utf-8")

    if as_json:
        click.echo(json.dumps(practice.to_dict(), indent=2))
    else:
        if show:
            print_header(f"Practice: {profile.name}")
        _render(practice, changed, path=path)
