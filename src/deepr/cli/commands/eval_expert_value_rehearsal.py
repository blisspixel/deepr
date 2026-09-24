"""Register the local four-arm operational rehearsal and its blinded review binding."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
from pydantic import ValidationError

from deepr.cli.commands.eval import evaluate
from deepr.evals.expert_value_artifacts import ArtifactVerificationError
from deepr.evals.expert_value_blinding import bind_review_labels, build_blind_assignment, reviewer_criteria
from deepr.evals.expert_value_rehearsal import (
    RehearsalPlan,
    RehearsalPolicy,
    RehearsalRun,
    plan_from_blueprint,
    runtime_preflight,
)
from deepr.evals.expert_value_sources import load_source_world_preparation

_FILE = click.Path(exists=True, dir_okay=False, path_type=Path)
_DIR = click.Path(exists=True, file_okay=False, path_type=Path)
_NEW = click.Path(dir_okay=False, path_type=Path)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise click.ClickException(f"Could not read {path.name}: {exc}") from exc


def _write_new(path: Path, payload: bytes) -> None:
    if path.exists():
        raise click.ClickException(f"Refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "xb") as handle:
        handle.write(payload)


@evaluate.group("expert-value-rehearsal")
def rehearsal() -> None:
    """Run and blind the local four-arm operational rehearsal ($0, unreviewed)."""


@rehearsal.command("plan")
@click.option("--blueprint", type=_FILE, required=True, help="Draft or accepted blueprint with acceptance cases.")
@click.option("--placement", type=_FILE, required=True, help="Organizer case placement mapping cases to worlds.")
@click.option("--output", type=_NEW, required=True, help="New question-only plan file.")
def plan_command(blueprint: Path, placement: Path, output: Path) -> None:
    """Extract a question-only case plan; criteria and roles are not copied."""
    try:
        plan = plan_from_blueprint(_read_json(blueprint), _read_json(placement))
    except (KeyError, ValidationError) as exc:
        raise click.ClickException(f"Invalid blueprint or placement: {exc}") from exc
    _write_new(output, (json.dumps(plan.model_dump(), indent=2, sort_keys=True) + "\n").encode("utf-8"))
    click.echo(f"Wrote {len(plan.cases)} question-only case(s) to {output}")


@rehearsal.command("run")
@click.option("--policy", "policy_path", type=_FILE, required=True, help="Frozen rehearsal policy JSON.")
@click.option("--plan", "plan_path", type=_FILE, required=True, help="Question-only plan JSON.")
@click.option("--from-file", "index_path", type=_FILE, required=True, help="Source-world preparation index.")
@click.option("--artifact-root", type=_DIR, required=True, help="Root containing the index and sources.")
@click.option("--run-root", type=click.Path(file_okay=False, path_type=Path), required=True, help="New run root.")
@click.option("--json", "json_output", is_flag=True, help="Emit the run summary as JSON.")
def run_command(
    policy_path: Path, plan_path: Path, index_path: Path, artifact_root: Path, run_root: Path, json_output: bool
) -> None:
    """Execute all cells on the owned local model; local calls are recorded at $0.

    Every phase runs in its own worker process with a verified source copy and
    no inherited credentials. Answers are saved unreviewed; no score or
    winner is produced.
    """
    try:
        policy = RehearsalPolicy.model_validate_json(policy_path.read_bytes())
        plan = RehearsalPlan.model_validate_json(plan_path.read_bytes())
        runtime = runtime_preflight(policy)
        run = RehearsalRun(
            policy=policy,
            plan=plan,
            index_path=index_path,
            artifact_root=artifact_root,
            run_root=run_root,
            runtime=runtime,
        )
    except (OSError, ValidationError, ValueError, ArtifactVerificationError) as exc:
        raise click.ClickException(f"Rehearsal refused before execution: {exc}") from exc
    summary = run.execute()
    if json_output:
        click.echo(json.dumps(summary, indent=2))
        return
    click.echo(
        f"{summary['status']}: {summary['terminal_cells']}/{summary['planned_cells']} terminal cells "
        f"({summary['answered']} answered, {summary['failed']} failed, {summary['blocked']} blocked); "
        f"ledger reconciled: {summary['ledger_reconciled']}; API cost $0. Answers are unreviewed."
    )


@rehearsal.command("blind")
@click.option("--run-root", type=_DIR, required=True, help="Completed rehearsal run root.")
@click.option("--blueprint", type=_FILE, required=True, help="Blueprint supplying reviewer criteria.")
@click.option("--placement", type=_FILE, required=True, help="Organizer case placement.")
@click.option("--from-file", "index_path", type=_FILE, required=True, help="Source-world preparation index.")
@click.option("--artifact-root", type=_DIR, required=True, help="Root containing the index and sources.")
@click.option("--rubric", type=_FILE, default=None, help="Optional reviewer rubric JSON.")
@click.option("--packet-out", type=_NEW, required=True, help="New reviewer packet (shareable).")
@click.option("--key-out", type=_NEW, required=True, help="New private assignment key (withhold).")
def blind_command(
    run_root: Path,
    blueprint: Path,
    placement: Path,
    index_path: Path,
    artifact_root: Path,
    rubric: Path | None,
    packet_out: Path,
    key_out: Path,
) -> None:
    """Write a blinded reviewer packet and a separate private assignment key."""
    if packet_out.absolute().parent == key_out.absolute().parent:
        raise click.ClickException("Keep the private key in a different directory from the reviewer packet")
    try:
        _, index, _, _, _ = load_source_world_preparation(index_path, artifact_root)
        cutoffs = {world.source_world_id: world.as_of for world in index.source_worlds}
        criteria = reviewer_criteria(_read_json(blueprint), _read_json(placement), cutoffs)
        packet, key = build_blind_assignment(run_root, criteria, rubric=_read_json(rubric) if rubric else None)
    except (KeyError, ValueError, ArtifactVerificationError) as exc:
        raise click.ClickException(f"Blinding refused: {exc}") from exc
    _write_new(packet_out, packet)
    _write_new(key_out, key)
    reviewable = json.loads(key)["reviewable_cells"]
    click.echo(f"Wrote a reviewer packet with {reviewable} blinded answer(s); keep {key_out.name} private.")


@rehearsal.command("bind-labels")
@click.option("--run-root", type=_DIR, required=True, help="Rehearsal run root holding the answers.")
@click.option("--key", "key_path", type=_FILE, required=True, help="Private assignment key.")
@click.option("--packet", "packet_path", type=_FILE, required=True, help="Reviewer packet the labels used.")
@click.option("--labels", "labels_path", type=_FILE, required=True, help="Frozen reviewer labels JSON.")
@click.option("--output", type=_NEW, required=True, help="New binding record.")
def bind_command(run_root: Path, key_path: Path, packet_path: Path, labels_path: Path, output: Path) -> None:
    """Join frozen labels to the key after one-to-one binding checks."""
    try:
        binding = bind_review_labels(
            run_root, key_path.read_bytes(), packet_path.read_bytes(), labels_path.read_bytes()
        )
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        raise click.ClickException(f"Label binding refused: {exc}") from exc
    _write_new(output, (json.dumps(binding, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    click.echo(f"Bound {len(binding['bound'])} label(s); reviewer identity and scores remain unverified.")


__all__ = ["rehearsal"]
