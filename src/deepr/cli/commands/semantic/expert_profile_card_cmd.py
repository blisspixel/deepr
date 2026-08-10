"""CLI: `deepr expert profile` - the expert's own account of how it reads its subject.

Everything else in the expert loop is about the material: what was retained,
what a lens found, which positions the findings support. None of it asks the
expert what it now thinks, and that is the difference between an index and
someone worth consulting.

This is also the missing rung. `expert health` reads `standpoint` from
`profile_card.json` for `has_perspective`, and nothing wrote that file, so the
top of the ladder was unreachable and the next action said "run profile" for a
command that did not exist.

The shift history is the part that matters most. Every study recomputes the
brief from the corpus, so nothing an expert concluded survives the next pass.
A profile is append-only: when a re-read moves the standpoint, the old one is
kept alongside what moved it. That history is the only place elapsed time
turns into something an expert has rather than something it has merely done.

$0. One model call, local or prepaid plan.
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
from deepr.experts.expert_profile_card import (
    ExpertProfile,
    build_profile_prompt,
    parse_profile,
)
from deepr.experts.model_provenance import record as provenance_record
from deepr.experts.paths import canonical_expert_dir
from deepr.utils.atomic_io import atomic_write_json

_MAX_MATERIAL_CHARS = 60_000


def canonical_profile_path(expert_name: str) -> Path:
    """Where the profile lives, and where `expert health` looks for it."""
    return canonical_expert_dir(expert_name) / "profile_card.json"


def _load_profile(name: str) -> Any:
    from deepr.experts.profile import ExpertStore

    stored = ExpertStore().load(name)
    if not stored:
        click.echo(f"Error: Expert not found: {name}", err=True)
        sys.exit(2)
    return stored


def _load_prior(expert_name: str) -> ExpertProfile | None:
    """The previous profile, so a change of mind can be recognised as one."""
    path = canonical_profile_path(expert_name)
    if not path.exists():
        return None
    try:
        return ExpertProfile.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        print_warning("Existing profile could not be read; writing a fresh one and losing its shift history.")
        return None


def _material(expert_name: str) -> tuple[str, str, int]:
    """What the expert has read: its brief and what the study found.

    Returns (material, corpus_fingerprint, sources_read). The fingerprint is
    carried so a later profile can tell "I re-read the same corpus and changed
    my mind" from "the corpus grew under me".
    """
    from deepr.experts.brief import render_brief
    from deepr.experts.consult_context import load_brief, load_study

    directory = canonical_expert_dir(expert_name)
    brief = load_brief(directory / "brief.json")
    if brief is None or not brief.positions:
        # An empty brief is worse than a missing one, because it looks like
        # material. Measured: a timed-out synthesis left a brief holding zero
        # positions and only a limitation, and profiling against it produced a
        # standpoint about the pipeline failing instead of about the subject.
        # The "did it return a standpoint" check cannot catch that - a
        # description of the failure is a perfectly non-empty standpoint.
        detail = "has no brief" if brief is None else "has a brief holding no positions"
        click.echo(
            f"Error: {expert_name} {detail}, so it has not landed anywhere to describe. "
            f'Run: deepr expert brief "{expert_name}"',
            err=True,
        )
        sys.exit(2)

    study = load_study(directory / "study.json")
    # The fingerprint lives on each LensOutcome, not on the result. Reading it
    # off the result returned "" every time, so the one field designed to
    # anchor a change of mind to a corpus state never held a value. Take the
    # newest lens's fingerprint: all lenses in a completed pass share one, and
    # in a resumed pass the newest is the corpus the standpoint was formed on.
    fingerprint = ""
    for outcome in reversed(list(getattr(study, "outcomes", []) or [])) if study else []:
        if candidate := str(getattr(outcome, "corpus_fingerprint", "") or ""):
            fingerprint = candidate
            break
    sources = int(getattr(getattr(study, "independence", None), "source_count", 0) or 0) if study else 0
    return render_brief(brief)[:_MAX_MATERIAL_CHARS], fingerprint, sources


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


def _render_lists(profile: ExpertProfile) -> None:
    """The three lists, in the order someone choosing an expert wants them.

    A table rather than three near-identical blocks: they differ only in
    heading, colour and which attribute they read, and writing that out three
    times is where the branch count came from.
    """
    sections = (
        ("Would be glad to be asked about", "cyan", profile.glad_to_be_asked_about, False),
        ("Still working on", "yellow", profile.open_questions, False),
        ("Knows it is weak on", "dim", profile.where_it_is_weak, True),
    )
    for heading, colour, items, dim_items in sections:
        if not items:
            continue
        console.print(f"\n[{colour}]{heading}[/{colour}]")
        for item in items:
            console.print(f"  [dim]- {item}[/dim]" if dim_items else f"  - {item}")


def _render(profile: ExpertProfile, *, path: Path) -> None:
    if profile.chosen_name:
        print_key_value("Calls itself", profile.chosen_name)
    if profile.standpoint:
        console.print(f"\n[bright_white]{profile.standpoint}[/bright_white]")
    if profile.preferred_lens:
        console.print(f"\n[dim]Reads it best through: {profile.preferred_lens}[/dim]")

    _render_lists(profile)

    if profile.shifts:
        console.print(f"\n[bright_yellow]Has changed its mind {len(profile.shifts)} time(s)[/bright_yellow]")
        for shift in profile.shifts[-3:]:
            console.print(f"  - was: {shift.was}")
            console.print(f"    now: {shift.now}")
            console.print(f"    [dim]because: {shift.because}[/dim]")

    for note in profile.concerns():
        print_warning(note)

    console.print()
    print_success(f"Written to {path}")


@expert.command(name="profile")
@click.argument("name")
@click.option("--local", is_flag=True, help="Use local Ollama ($0)")
@click.option("--plan", default=None, help="Prepaid plan backend id (e.g. claude)")
@click.option("--plan-model", default=None, help="Model for the plan backend")
@click.option("--model", default=None, help="Explicit local model")
@click.option("--json", "as_json", is_flag=True, help="Emit the profile JSON")
def expert_profile_cmd(
    name: str,
    local: bool,
    plan: str | None,
    plan_model: str | None,
    model: str | None,
    as_json: bool,
) -> None:
    """Ask NAME to account for how it reads its own subject ($0).

    Produces a standpoint, what it thinks the real question is, what it is
    still working on, where it knows it is weak, and what it would be glad to
    be asked. `expert health` reads this for the perspective rung, and a
    consult uses it to speak as itself rather than as a summary.

    Re-running after new material is the point. If the standpoint moved, the
    old one is kept with what moved it, because the history of changing its
    mind is the part that cannot be recomputed.

    EXAMPLES:

      deepr expert profile "My Expert"
      deepr expert profile "My Expert" --plan claude
    """
    stored = _load_profile(name)
    material, fingerprint, sources = _material(stored.name)
    prior = _load_prior(stored.name)

    try:
        backend = build_study_backend(profile=stored, local=local, plan=plan, plan_model=plan_model, model=model)
    except StudyBackendError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(2)

    if not as_json:
        print_header(f"Profile: {stored.name}")
        print_key_value("Capacity", backend.cost_note)
        if prior is not None:
            print_key_value("Prior standpoint", "shown, so a change of mind can be recorded as one")

    try:
        raw = asyncio.run(backend.completion(build_profile_prompt(stored.name, material=material, prior=prior)))
    except Exception as exc:
        click.echo(f"Error: the model call failed: {type(exc).__name__}: {exc}", err=True)
        sys.exit(2)

    parsed = _parse_json(raw)
    profile = parse_profile(
        parsed,
        expert_name=stored.name,
        at=datetime.now(UTC).isoformat(),
        prior=prior,
        corpus_fingerprint=fingerprint,
        sources_read=sources,
    )

    # Refuse before writing. An unparsed reply would otherwise replace a real
    # profile with an empty one and take its whole shift history with it,
    # which is the only unrecomputable thing in an expert's directory.
    if not profile.has_standpoint:
        click.echo(
            "Error: the model returned no usable standpoint, so nothing was written. "
            "Any existing profile has been left alone.",
            err=True,
        )
        sys.exit(2)

    # Stamp which model wrote this. A standpoint is the most model-dependent
    # artifact an expert has: it is the one place the reading is asked for
    # directly rather than derived from the corpus, so knowing what produced it
    # matters more here than anywhere else.
    payload = profile.to_dict()
    payload["model_provenance"] = provenance_record(backend.capacity_source, backend.model).to_dict()

    path = canonical_profile_path(stored.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, payload, fsync=True)

    if as_json:
        click.echo(json.dumps(payload, indent=2))
    else:
        _render(profile, path=path)
