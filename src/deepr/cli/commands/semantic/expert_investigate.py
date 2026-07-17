"""Evidence-first expert investigation CLI."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import click

from deepr.cli.colors import print_info, print_success, print_warning
from deepr.cli.commands.semantic.experts import expert
from deepr.experts.investigation.executor import InvestigationExecutor
from deepr.experts.investigation.models import (
    DEFAULT_LOCAL_CONTEXT_WINDOW_TOKENS,
    MAX_LOCAL_CONTEXT_WINDOW_TOKENS,
    MIN_LOCAL_CONTEXT_WINDOW_TOKENS,
    InvestigationBounds,
    InvestigationContractError,
    RunState,
    remaining_capacity,
    validate_plan,
)
from deepr.experts.investigation.ollama_backend import NativeOllamaInvestigationBackend
from deepr.experts.investigation.planner import build_investigation_plan
from deepr.experts.investigation.store import (
    InvestigationBusyError,
    InvestigationNotFoundError,
    InvestigationStorageError,
    InvestigationStore,
)
from deepr.utils.atomic_io import atomic_write_json


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise click.ClickException(f"Could not read trusted JSON from {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise click.ClickException(f"Expected a JSON object in {path}")
    return payload


def _emit_json(payload: dict[str, Any]) -> None:
    click.echo(json.dumps(payload, indent=2, sort_keys=True))


def _plan_summary(plan: dict[str, Any]) -> dict[str, Any]:
    bundle = plan["input_bundle"]
    return {
        "schema_version": plan["schema_version"],
        "kind": plan["kind"],
        "run_id": plan["run_id"],
        "plan_sha256": plan["plan_sha256"],
        "question": plan["question"],
        "experts": [
            {
                "name": item["name"],
                "domain": item.get("domain", ""),
                "snapshot_sha256": item["snapshot_sha256"],
                "readiness": item.get("readiness", {}),
            }
            for item in plan["experts"]
        ],
        "protocol": plan["protocol"],
        "learning": plan["learning"],
        "capacity": plan["capacity"],
        "bounds": plan["bounds"],
        "call_formula": plan["call_formula"],
        "retrieval": plan["retrieval"],
        "input_summary": bundle["summary"],
        "included_paths": [item["display_path"] for item in bundle["items"] if item["input_type"] == "file"],
        "requested_urls": [item["url"] for item in bundle["items"] if item["input_type"] == "url"],
        "exclusions": bundle["exclusions"],
        "data_egress": plan["data_egress"],
        "learning_contract": plan["learning_contract"],
        "preview_activity": plan["preview_activity"],
    }


def _render_plan(plan: dict[str, Any]) -> None:
    summary = _plan_summary(plan)
    bounds = summary["bounds"]
    click.echo(f"Run id: {summary['run_id']}")
    click.echo(f"Plan hash: {summary['plan_sha256']}")
    click.echo(f"Protocol: {summary['protocol']}")
    if summary["learning"] == "stage":
        click.echo("Learning: stage (source-only, domain-relevance-gated proposals; no expert-state writes)")
    else:
        click.echo("Learning: off")
    click.echo(f"Expert model: {summary['capacity']['model']}")
    click.echo(f"Review model: {summary['capacity'].get('review_model', summary['capacity']['model'])}")
    click.echo(
        "Context windows: "
        f"expert {summary['capacity'].get('context_window_tokens', DEFAULT_LOCAL_CONTEXT_WINDOW_TOKENS)}, "
        "review "
        f"{summary['capacity'].get('review_context_window_tokens', DEFAULT_LOCAL_CONTEXT_WINDOW_TOKENS)} tokens"
    )
    click.echo("Fallback: none")
    click.echo("Maximum provider spend: $0.00")
    click.echo(f"Maximum generation calls: {bounds['max_generation_calls']}")
    click.echo(f"Maximum search queries: {bounds['max_search_queries']}")
    click.echo(f"Maximum page fetches: {bounds['max_page_fetches']}")
    click.echo(f"Maximum input tokens: {bounds['max_input_tokens']}")
    click.echo(f"Maximum output tokens: {bounds['max_output_tokens']}")
    click.echo(f"Maximum prompt bytes per call: {bounds['max_prompt_bytes_per_call']}")
    click.echo(f"Maximum output tokens per call: {bounds['max_output_tokens_per_call']}")
    click.echo(f"Maximum elapsed seconds: {bounds['max_elapsed_seconds']}")
    click.echo(f"Maximum local artifact bytes: {bounds['max_disk_bytes']}")
    click.echo(f"Maximum concurrency: {bounds['max_concurrency']}")
    click.echo(f"Experts ({len(summary['experts'])}):")
    for item in summary["experts"]:
        readiness = item["readiness"]
        click.echo(
            f"  - {item['name']}: {readiness.get('claim_count', 0)} claims, "
            f"{readiness.get('verified_claim_count', 0)} verified, "
            f"{readiness.get('open_gap_count', 0)} open gaps, blueprint {readiness.get('blueprint_status', 'unknown')}"
        )
    inputs = summary["input_summary"]
    click.echo(
        f"Inputs: {inputs['included_items']} included, {inputs['excluded_paths']} excluded, "
        f"{inputs['local_input_bytes']} local bytes"
    )
    for exclusion in summary["exclusions"]:
        click.echo(f"  excluded {exclusion['path']}: {exclusion['reason']}")
    click.echo("Preview activity: 0 model calls, 0 network requests, 0 expert-state writes, $0.00")
    print_warning("Execution performs public web retrieval. The zero-network guarantee applies only to this preview.")
    print_warning(
        "Ollama readiness was not probed during preview. Execution fails closed if the pinned model is unavailable."
    )


def _status_payload(store: InvestigationStore, run_id: str) -> dict[str, Any]:
    plan = store.load_plan(run_id)
    state = store.load_state(run_id)
    bounds = InvestigationBounds.from_dict(plan["bounds"])
    return {
        "run_id": run_id,
        "plan_sha256": plan["plan_sha256"],
        "state": state["state"],
        "phase": state["phase"],
        "version": state["version"],
        "usage": state["usage"],
        "remaining": remaining_capacity(bounds, state["usage"]),
        "control": store.load_control(run_id),
        "artifact_count": len(state.get("artifacts", {})),
        "errors": state.get("errors", []),
        "run_dir": str(store.run_dir(run_id)),
    }


def _inspection_payload(store: InvestigationStore, run_id: str) -> dict[str, Any]:
    state = store.load_state(run_id)
    artifacts = state.get("artifacts", {})

    def read(logical_key: str) -> dict[str, Any] | None:
        reference = artifacts.get(logical_key) if isinstance(artifacts, dict) else None
        return store.read_artifact(run_id, reference) if isinstance(reference, dict) else None

    positions: dict[str, Any] = {}
    if isinstance(artifacts, dict):
        for logical_key, reference in artifacts.items():
            if not isinstance(reference, dict) or not logical_key.startswith(("position:", "revision:")):
                continue
            positions[logical_key] = store.read_artifact(run_id, reference)
    return {
        "status": _status_payload(store, run_id),
        "plan": _plan_summary(store.load_plan(run_id)),
        "result": read("result"),
        "check": read("check"),
        "learning_manifest": read("learning:manifest"),
        "positions": positions,
        "events": store.load_events(run_id),
    }


def _render_status(payload: dict[str, Any]) -> None:
    click.echo(f"Run id: {payload['run_id']}")
    click.echo(f"State: {payload['state']}")
    click.echo(f"Phase: {payload['phase']}")
    click.echo(f"Generation calls: {payload['usage']['generation_calls']}")
    click.echo(f"Search queries: {payload['usage']['search_queries']}")
    click.echo(f"Page fetches: {payload['usage']['page_fetches']}")
    click.echo(f"Provider cost: ${float(payload['usage']['cost_usd']):.2f}")
    click.echo(f"Artifacts: {payload['artifact_count']}")
    click.echo(f"Run directory: {payload['run_dir']}")
    if payload["errors"]:
        click.echo(f"Last stop: {payload['errors'][-1]['error_type']}: {payload['errors'][-1]['message']}")


def _render_learning(payload: dict[str, Any], learning: dict[str, Any]) -> None:
    click.echo("\nStaged learning")
    summary = learning.get("summary", {})
    click.echo(f"Experts with verifier-ready writes: {summary.get('automatic_verifier_accepted_count', 0)}")
    click.echo(f"Total verifier-ready writes: {summary.get('ready_write_count', 0)}")
    click.echo("Target-domain relevance required: yes")
    click.echo("Human reviewed: 0")
    click.echo("Expert-state writes: 0")
    for entry in learning.get("entries", []):
        click.echo(
            f"  - {entry.get('expert_name')}: {entry.get('status')}, {entry.get('ready_write_count', 0)} staged writes"
        )
        if entry.get("reason"):
            click.echo(f"    Reason: {entry['reason']}")
        envelope = entry.get("graph_commit_envelope_artifact")
        ready_writes = int(entry.get("ready_write_count", 0) or 0)
        if envelope and ready_writes > 0:
            full_path = Path(payload["status"]["run_dir"]) / str(envelope)
            click.echo(
                f"    Preview apply: deepr expert apply-graph-commit {json.dumps(entry.get('expert_name'))} "
                f"{json.dumps(str(full_path))} --dry-run --json"
            )
        elif envelope:
            click.echo("    No applicable graph writes passed the automatic verifier.")


def _render_inspection(payload: dict[str, Any]) -> None:
    _render_status(payload["status"])
    result = payload.get("result")
    if isinstance(result, dict):
        click.echo(
            "Semantic quality: "
            f"{result.get('semantic_review_status', 'unreviewed')} "
            "(structural completion is not a quality claim)"
        )
        click.echo("\nAnswer")
        click.echo(str(result.get("answer", "")))
        contributions = result.get("expert_contributions", [])
        if contributions:
            click.echo("\nExpert contributions")
            for contribution in contributions:
                click.echo(
                    f"  - {contribution.get('expert_name')}: {contribution.get('status')} - "
                    f"{contribution.get('contribution') or contribution.get('reason', '')}"
                )
        for label, key in (
            ("Disagreements", "disagreements"),
            ("Minority positions", "minority_positions"),
            ("Uncertainties", "uncertainties"),
            ("Next tests", "next_tests"),
        ):
            values = result.get(key, [])
            if values:
                click.echo(f"\n{label}")
                for value in values:
                    click.echo(f"  - {value}")
    learning = payload.get("learning_manifest")
    if isinstance(learning, dict):
        _render_learning(payload, learning)


def _confirmed(plan: dict[str, Any], yes: bool) -> bool:
    if yes:
        return True
    if not sys.stdin.isatty():
        return False
    calls = int(plan["bounds"]["max_generation_calls"])
    pages = int(plan["bounds"]["max_page_fetches"])
    return click.confirm(
        f"Run up to {calls} local model calls and {pages} public page fetches with $0 maximum provider spend?",
        default=False,
    )


def _execute_run(store: InvestigationStore, plan: dict[str, Any]) -> dict[str, Any]:
    model = str(plan["capacity"]["model"])
    backend = NativeOllamaInvestigationBackend(model=model)
    executor = InvestigationExecutor(store=store, backend=backend)
    return asyncio.run(executor.run_plan(plan))


def _exit_for_state(state: str) -> None:
    if state == RunState.COMPLETED.value:
        return
    if state in {RunState.PAUSED.value, RunState.CANCELLED.value}:
        raise click.exceptions.Exit(2)
    raise click.exceptions.Exit(1)


@expert.group(name="investigate")
def expert_investigate() -> None:
    """Plan, run, and inspect bounded multi-expert research."""


@expert_investigate.command(name="plan")
@click.argument("question")
@click.option("--expert", "experts", multiple=True, required=True, help="Existing expert, repeatable.")
@click.option("--text", "inline_texts", multiple=True, help="Caller-supplied inline context, repeatable.")
@click.option(
    "--url",
    "urls",
    multiple=True,
    help="Public URL offered as an evidence candidate during execution, repeatable.",
)
@click.option("--file", "files", multiple=True, type=click.Path(path_type=Path), help="Input file, repeatable.")
@click.option("--folder", "folders", multiple=True, type=click.Path(path_type=Path), help="Input folder, repeatable.")
@click.option(
    "--input-root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path.cwd,
    show_default="current directory",
    help="Root that confines all file and folder inputs.",
)
@click.option("--capacity", type=click.Choice(["local"]), default="local", show_default=True)
@click.option("--budget-usd", type=float, default=0.0, show_default=True, help="V1 local plans require exactly 0.")
@click.option("--local-model", help="Exact Ollama model. Required when expert profile models differ.")
@click.option(
    "--review-model",
    help="Optional exact Ollama model for checking, synthesis, and staged claim verification.",
)
@click.option(
    "--context-window-tokens",
    type=click.IntRange(MIN_LOCAL_CONTEXT_WINDOW_TOKENS, MAX_LOCAL_CONTEXT_WINDOW_TOKENS),
    default=DEFAULT_LOCAL_CONTEXT_WINDOW_TOKENS,
    show_default=True,
    help="Pinned native Ollama context for expert calls.",
)
@click.option(
    "--review-context-window-tokens",
    type=click.IntRange(MIN_LOCAL_CONTEXT_WINDOW_TOKENS, MAX_LOCAL_CONTEXT_WINDOW_TOKENS),
    help="Pinned native Ollama context for checking, synthesis, and staged claim verification.",
)
@click.option(
    "--protocol",
    type=click.Choice(["independent", "discuss", "deep"]),
    default="discuss",
    show_default=True,
)
@click.option("--learning", type=click.Choice(["off", "stage"]), default="off", show_default=True)
@click.option("--max-elapsed-seconds", type=click.FloatRange(min=1.0, max=21_600.0), default=3600.0)
@click.option("--out", type=click.Path(dir_okay=False, path_type=Path), help="Write the immutable plan here.")
@click.option("--json", "json_output", is_flag=True, help="Emit the complete immutable plan as JSON.")
def investigate_plan(
    question: str,
    experts: tuple[str, ...],
    inline_texts: tuple[str, ...],
    urls: tuple[str, ...],
    files: tuple[Path, ...],
    folders: tuple[Path, ...],
    input_root: Path,
    capacity: str,
    budget_usd: float,
    local_model: str | None,
    review_model: str | None,
    context_window_tokens: int,
    review_context_window_tokens: int | None,
    protocol: str,
    learning: str,
    max_elapsed_seconds: float,
    out: Path | None,
    json_output: bool,
) -> None:
    """Preview an immutable zero-call, zero-network investigation plan."""
    if capacity != "local" or budget_usd != 0.0:
        raise click.UsageError("V1 investigation plans support local capacity with --budget-usd 0 only.")
    try:
        plan = build_investigation_plan(
            question=question,
            expert_names=experts,
            input_root=input_root,
            inline_texts=inline_texts,
            urls=urls,
            files=files,
            folders=folders,
            local_model=local_model,
            review_model=review_model,
            context_window_tokens=context_window_tokens,
            review_context_window_tokens=review_context_window_tokens,
            protocol=protocol,
            learning=learning,
            max_elapsed_seconds=max_elapsed_seconds,
        )
    except InvestigationContractError as exc:
        raise click.ClickException(str(exc)) from exc
    if out is not None:
        try:
            atomic_write_json(out, plan, indent=2, sort_keys=True, fsync=True)
        except OSError as exc:
            raise click.ClickException(f"Could not write investigation plan: {exc}") from exc
    if json_output:
        _emit_json(plan)
    else:
        _render_plan(plan)
        if out is not None:
            print_success(f"Wrote immutable plan: {out}")


@expert_investigate.command(name="run")
@click.argument("plan_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--yes", "-y", is_flag=True, help="Confirm local calls and public retrieval noninteractively.")
@click.option("--json", "json_output", is_flag=True, help="Emit the inspection payload as JSON.")
def investigate_run(plan_path: Path, yes: bool, json_output: bool) -> None:
    """Execute a hash-bound local plan with no provider fallback."""
    try:
        plan = validate_plan(_load_json(plan_path))
    except InvestigationContractError as exc:
        raise click.ClickException(str(exc)) from exc
    if not _confirmed(plan, yes):
        raise click.UsageError("Execution requires interactive confirmation or --yes.")
    store = InvestigationStore()
    try:
        state = _execute_run(store, plan)
        payload = _inspection_payload(store, str(plan["run_id"]))
    except (InvestigationBusyError, InvestigationStorageError) as exc:
        raise click.ClickException(str(exc)) from exc
    except Exception as exc:
        raise click.ClickException(f"Investigation failed: {exc}") from exc
    if json_output:
        _emit_json(payload)
    else:
        _render_inspection(payload)
        if state["state"] == "completed":
            print_success("Investigation completed with $0 provider spend and no expert-state writes.")
    _exit_for_state(str(state["state"]))


@expert_investigate.command(name="status")
@click.argument("run_id")
@click.option("--json", "json_output", is_flag=True)
def investigate_status(run_id: str, json_output: bool) -> None:
    """Show durable state and remaining parent capacity."""
    try:
        payload = _status_payload(InvestigationStore(), run_id)
    except (InvestigationNotFoundError, InvestigationStorageError) as exc:
        raise click.ClickException(str(exc)) from exc
    if json_output:
        _emit_json(payload)
    else:
        _render_status(payload)


@expert_investigate.command(name="inspect")
@click.argument("run_id")
@click.option("--json", "json_output", is_flag=True)
def investigate_inspect(run_id: str, json_output: bool) -> None:
    """Inspect cited results, dissent, traces, and staged learning."""
    try:
        payload = _inspection_payload(InvestigationStore(), run_id)
    except (InvestigationNotFoundError, InvestigationStorageError) as exc:
        raise click.ClickException(str(exc)) from exc
    if json_output:
        _emit_json(payload)
    else:
        _render_inspection(payload)


def _request_control(run_id: str, action: str, *, json_output: bool) -> None:
    store = InvestigationStore()
    try:
        control = store.request_control(run_id, action)
        payload = _status_payload(store, run_id)
    except (InvestigationNotFoundError, InvestigationStorageError) as exc:
        raise click.ClickException(str(exc)) from exc
    payload["control"] = control
    if json_output:
        _emit_json(payload)
    else:
        print_info(f"Requested {action} for {run_id}.")
        _render_status(payload)


@expert_investigate.command(name="pause")
@click.argument("run_id")
@click.option("--json", "json_output", is_flag=True)
def investigate_pause(run_id: str, json_output: bool) -> None:
    """Request a pause before the next dispatch."""
    _request_control(run_id, "pause", json_output=json_output)


@expert_investigate.command(name="cancel")
@click.argument("run_id")
@click.option("--json", "json_output", is_flag=True)
def investigate_cancel(run_id: str, json_output: bool) -> None:
    """Request cancellation and reject later artifact side effects."""
    _request_control(run_id, "cancel", json_output=json_output)


@expert_investigate.command(name="resume")
@click.argument("run_id")
@click.option("--yes", "-y", is_flag=True, help="Confirm continued local calls and public retrieval.")
@click.option("--json", "json_output", is_flag=True)
def investigate_resume(run_id: str, yes: bool, json_output: bool) -> None:
    """Resume a paused run from verified phase artifacts."""
    store = InvestigationStore()
    try:
        plan = store.load_plan(run_id)
        state = store.load_state(run_id)
    except (InvestigationNotFoundError, InvestigationStorageError) as exc:
        raise click.ClickException(str(exc)) from exc
    if state["state"] != RunState.PAUSED.value:
        raise click.UsageError(f"Only paused investigations can resume; current state is {state['state']}.")
    if not _confirmed(plan, yes):
        raise click.UsageError("Resume requires interactive confirmation or --yes.")
    store.request_control(run_id, "run")
    try:
        resumed = _execute_run(store, plan)
        payload = _inspection_payload(store, run_id)
    except (InvestigationBusyError, InvestigationStorageError) as exc:
        raise click.ClickException(str(exc)) from exc
    except Exception as exc:
        raise click.ClickException(f"Investigation resume failed: {exc}") from exc
    if json_output:
        _emit_json(payload)
    else:
        _render_inspection(payload)
    _exit_for_state(str(resumed["state"]))


__all__ = ["expert_investigate"]
