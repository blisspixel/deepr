"""CLI: `deepr expert status` - where one expert is in the loop, and why.

The loop is seven stages, each writing a JSON file the next reads. Asked what
was wrong with that as a harness, Deepr's own harness-design expert answered:

    Loose JSON handoffs create hidden coupling. Schema drift, partial writes,
    stale files, incompatible versions and missing provenance can silently
    corrupt later stages. [...] Producing every JSON file does not prove the
    final result is correct.

Both halves happened here in one afternoon. A synthesis timed out; a brief was
written holding zero positions; the command exited 0 printing the path. The
profile stage read that file, found it present and parseable, and produced a
standpoint about *the pipeline failing* rather than about the subject.

``stage_contract`` encodes the fix declaratively. This is the surface that
makes it visible: what is done, what is ready, what is blocked and by what, and
- the one no existing view could show - what **failed**, meaning the artifact
exists and does not carry what it promised.

$0. Reads files, calls no model, touches no network.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import click

from deepr.cli.colors import console, print_header, print_key_value, print_warning
from deepr.cli.commands.semantic.experts import expert
from deepr.experts.expert_layout import resolve_relative
from deepr.experts.paths import canonical_expert_dir
from deepr.experts.stage_contract import STAGES, evaluate_all, next_stage

_STATUS_COLOR = {"done": "green", "ready": "cyan", "failed": "red", "blocked": "yellow"}

_STATUS_MEANING = {
    "done": "produced what it promised",
    "ready": "inputs are satisfied, has not run",
    "failed": "the artifact exists and carries nothing",
    "blocked": "an input is missing or empty",
}


def _load_profile(name: str) -> Any:
    from deepr.experts.profile import ExpertStore

    profile = ExpertStore().load(name)
    if not profile:
        click.echo(f"Error: Expert not found: {name}", err=True)
        sys.exit(2)
    return profile


def _read_artifacts(directory: Path) -> dict[str, dict[str, Any] | None]:
    """Load every artifact the contract refers to, or None where unusable.

    Missing and unparseable are deliberately the same value. An input that
    cannot be read is no more usable than one that is absent, and treating a
    corrupt file as present is how the corruption reaches the next stage.
    """
    wanted = {stage.produces for stage in STAGES if stage.produces}
    wanted |= {requirement.artifact for stage in STAGES for requirement in stage.requires}

    artifacts: dict[str, dict[str, Any] | None] = {}
    for relative in sorted(wanted):
        path = resolve_relative(directory, relative)
        if not path.exists():
            artifacts[relative] = None
            continue
        try:
            if path.suffix == ".jsonl":
                # The corpus index is a line-per-source log; the contract only
                # asks how many are active, so count rather than parse each.
                active = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
                artifacts[relative] = {"active_count": active}
            else:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                artifacts[relative] = loaded if isinstance(loaded, dict) else None
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            artifacts[relative] = None
    return artifacts


@expert.command(name="status")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True, help="Emit the stage states as JSON")
def expert_status(name: str, as_json: bool) -> None:
    """Show where NAME is in the loop, and what is blocking it ($0, no model).

    Four states, and the third is the one no other view could show:

    \b
      done     produced what it promised
      ready    inputs satisfied, has not run
      failed   the artifact exists and carries nothing
      blocked  an input is missing or empty

    A stage that wrote a file is not a stage that produced a result. Checking
    only for presence is what let a timed-out brief become a standpoint about
    the pipeline failing.

    EXAMPLES:

      deepr expert status "My Expert"
    """
    profile = _load_profile(name)
    states = evaluate_all(_read_artifacts(canonical_expert_dir(profile.name)))

    if as_json:
        payload = {
            "expert": profile.name,
            "stages": [state.to_dict() for state in states],
            "next": (nxt.name if (nxt := next_stage(states)) else None),
            "cost_usd": 0.0,
        }
        click.echo(json.dumps(payload, indent=2))
        return

    print_header(f"Status: {profile.name}")
    for state in states:
        colour = _STATUS_COLOR.get(state.status, "white")
        console.print(f"  [{colour}]{state.status:8s}[/{colour}] {state.name:10s} [dim]{state.success_means}[/dim]")
        for blocker in state.blockers:
            console.print(f"             [dim]blocked: {blocker.reason}[/dim]")
            console.print(f"             [dim]         fix with `deepr {blocker.fix}`[/dim]")

    console.print()
    if failed := [s for s in states if s.status == "failed"]:
        print_warning(
            f"{len(failed)} stage(s) wrote an artifact that carries nothing. Re-run those before "
            "building on top of them - a later stage cannot tell the difference."
        )

    if nxt := next_stage(states):
        print_key_value("Next", f"{nxt.name} - {_STATUS_MEANING[nxt.status]}")
    else:
        print_key_value("Next", "nothing; every stage has produced what it promised")
