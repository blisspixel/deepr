"""`deepr capacity` - show research capacity sources (read-only, $0).

Surfaces what capacity is available - local hardware, plan-quota CLIs, metered
APIs - so the operator can see the owned/prepaid capacity that capacity-aware
routing drains before touching a metered API. Visibility only today: this
detects sources and never runs research or spends. Design:
docs/design/capacity-waterfall.md.
"""

from __future__ import annotations

import json as _json

import click

from deepr.backends.capacity import BackendKind, detect_capacity
from deepr.backends.quota_ledger import QuotaState, summarize_quota_state

_GROUP_ORDER = [
    (BackendKind.LOCAL, "Local (free at the margin)"),
    (BackendKind.PLAN_QUOTA, "Plan quota (prepaid - your subscriptions)"),
    (BackendKind.API_METERED, "Metered API (paid per call - last resort)"),
]


@click.group(name="capacity", invoke_without_command=True)
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
@click.option("--probe", is_flag=True, help="Do a $0 round-trip to the local model to confirm it works.")
@click.pass_context
def capacity(ctx: click.Context, json_output: bool, probe: bool):
    """Show available research capacity (local, plan quota, metered API).

    Capacity-aware routing (v2.16) drains owned and prepaid capacity before any
    metered API call. With no subcommand this shows what capacity is available
    (runs no research, spends nothing); --probe does one tiny $0 round-trip to
    the local Ollama model to confirm local execution actually works.

    Admit a local model for automatic owned-capacity-first maintenance with
    `deepr capacity admit`; list or revoke admissions with `admissions` /
    `revoke`.
    """
    # Group with a default action: only run the status view when no subcommand
    # was given (e.g. `deepr capacity admit ...` skips this body).
    if ctx.invoked_subcommand is not None:
        return

    sources = detect_capacity()
    quota_states = summarize_quota_state()

    if probe and not json_output:
        _print_local_probe()

    if json_output:
        click.echo(_json.dumps([_source_to_dict(s, quota_states) for s in sources], indent=2))
        return

    _print_sources(sources)
    _print_quota_summary(quota_states)
    _print_admissions_summary()


def _source_to_dict(source, quota_states: list[QuotaState]) -> dict[str, object]:
    d = source.to_dict()
    states = _quota_states_for(source.backend_id, quota_states)
    state = _primary_quota_state(states)
    d["quota_state"] = state.to_dict() if state else None
    d["quota_states"] = [s.to_dict() for s in states]
    return d


def _quota_states_for(backend_id: str, quota_states: list[QuotaState]) -> list[QuotaState]:
    if not backend_id:
        return []
    return [state for state in quota_states if state.backend_id == backend_id]


def _primary_quota_state(quota_states: list[QuotaState]) -> QuotaState | None:
    if not quota_states:
        return None
    return next((state for state in quota_states if not state.account_id), quota_states[0])


def _print_local_probe() -> None:
    """One $0 round-trip to the local model, with a human-readable verdict."""
    from deepr.backends.local import probe_local
    from deepr.cli.async_runner import run_async_command

    result = run_async_command(probe_local())
    if result["ok"]:
        click.echo(
            f"Local probe: OK - {result['model']} replied {result['reply']!r} in {result['latency_ms']}ms (cost $0)\n"
        )
    else:
        click.echo(f"Local probe: FAILED - {result['error']}\n")


def _print_sources(sources) -> None:
    """Print detected capacity grouped cheapest-first, then a one-line summary."""
    click.echo("Research capacity (used in order: local -> plan quota -> metered API)\n")
    for kind, heading in _GROUP_ORDER:
        group = [s for s in sources if s.kind == kind]
        if not group:
            continue
        click.echo(heading)
        for s in group:
            mark = "+" if s.available else "-"
            status = "available" if s.available else "not available"
            click.echo(f"  [{mark}] {s.name:24s} {status:14s} {s.marginal_cost:16s} {s.detail}")
        click.echo("")

    local_or_plan = [s for s in sources if s.kind in (BackendKind.LOCAL, BackendKind.PLAN_QUOTA) and s.available]
    if local_or_plan:
        names = ", ".join(s.name for s in local_or_plan)
        click.echo(f"Owned/prepaid capacity available: {names}")
    else:
        click.echo(
            "No owned/prepaid capacity detected. Install Ollama or a plan CLI to research without per-call cost."
        )
    click.echo("Note: CLI 'available' means installed on PATH only - auth, quota window, and overflow")
    click.echo("state are verified by the adapter at run time. Only the local probe (--probe) round-trips.")


def _print_quota_summary(quota_states: list[QuotaState]) -> None:
    """Show latest observed quota state from the local append-only ledger."""
    click.echo("")
    if not quota_states:
        click.echo("No plan quota observations recorded yet.")
        return

    click.echo("Observed quota state (local ledger):")
    for state in quota_states:
        event = state.latest_event
        mark = "!" if state.exhausted or state.quarantined else "+"
        status = "quarantined" if state.quarantined else "exhausted" if state.exhausted else event.event_type.value
        remaining = _format_remaining(event.units_remaining, event.unit_name)
        confidence = event.remaining_confidence.value
        reset = f", resets {event.reset_at.isoformat()}" if event.reset_at else ""
        detail = f" - {event.detail}" if event.detail else ""
        click.echo(f"  [{mark}] {state.key:18s} {status:24s} {remaining} ({confidence}){reset}{detail}")


def _format_remaining(units_remaining: float | None, unit_name: str) -> str:
    if units_remaining is None:
        return "remaining unknown"
    return f"{units_remaining:g} {unit_name} remaining"


def _print_admissions_summary() -> None:
    """List local models admitted for the automatic owned-capacity-first path."""
    from deepr.backends.admission import list_active

    admitted = list_active()
    click.echo("")
    if admitted:
        click.echo("Local models admitted for automatic owned-capacity-first maintenance:")
        for a in admitted:
            exp = a.expires_at.strftime("%Y-%m-%d") if a.expires_at else "never"
            click.echo(f"  [+] {a.model} for {a.task_class} (expires {exp})")
    else:
        click.echo("No local models admitted yet. `deepr capacity admit <model> --task-class sync` lets")
        click.echo("`expert sync`/`absorb` use a local model automatically (review quality first).")


@capacity.command(name="next")
@click.option("--task-class", default="sync", show_default=True, help="Task class to plan for, e.g. sync or absorb.")
@click.option(
    "--expert", "expert_name", default="<expert>", show_default=True, help="Expert name for command previews."
)
@click.option("--report-id", default="<report_id>", show_default=True, help="Report id for absorb command previews.")
@click.option(
    "--context-mode",
    type=click.Choice(["none", "fresh", "deep"]),
    default="none",
    show_default=True,
    help="Concrete sync context mode to preview.",
)
@click.option("--scheduled", is_flag=True, help="Prefer wait guidance for recurring scheduler work.")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def capacity_next(
    task_class: str,
    expert_name: str,
    report_id: str,
    context_mode: str,
    scheduled: bool,
    json_output: bool,
):
    """Show the next safe actions for using cheap capacity.

    Read-only and $0: explains whether automatic local routing is ready, why it
    is blocked, and which command most directly unblocks it.
    """
    from deepr.backends.capacity_actions import (
        CapacityJobContext,
        build_capacity_next_actions,
        build_capacity_next_payload,
    )

    try:
        job_context = CapacityJobContext(
            task_class=task_class,
            expert_name=expert_name,
            report_id=report_id,
            context_mode=context_mode,
            scheduled=scheduled,
        )
        actions = build_capacity_next_actions(task_class=task_class, job_context=job_context)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    if json_output:
        payload = build_capacity_next_payload(job_context, actions)
        click.echo(_json.dumps(payload, indent=2))
        return

    click.echo(f"Capacity next actions for task class: {task_class}\n")
    if context_mode != "none" or scheduled or expert_name != "<expert>" or report_id != "<report_id>":
        click.echo(
            f"Job preview: expert={expert_name}, report_id={report_id}, context={context_mode}, scheduled={scheduled}\n"
        )
    if not actions:
        click.echo("No next actions found.")
        return

    for action in actions:
        click.echo(f"{action.rank}. {action.title} [{action.status}]")
        click.echo(f"   {action.detail}")
        if action.command:
            click.echo(f"   {action.command}")


@capacity.command(name="admit")
@click.argument("model", required=False)
@click.option(
    "--task-class",
    "task_class",
    required=True,
    help="Task class this model is admitted for (e.g. sync, absorb).",
)
@click.option("--days", type=int, default=None, help="Admission lifetime in days (default 90).")
@click.option("--score", type=float, default=None, help="Optional quality score from your review/eval.")
@click.option(
    "--from-eval",
    "eval_path",
    type=str,
    default=None,
    help="Use a saved `deepr eval local --save` artifact path, or 'latest'.",
)
@click.option(
    "--min-score",
    type=float,
    default=None,
    help="Minimum artifact score required with --from-eval (default 0.70).",
)
@click.option("--note", default="", help="Optional note (e.g. how you validated quality).")
@click.option("--yes", "-y", is_flag=True, help="Skip the confirmation prompt.")
def capacity_admit(
    model: str | None,
    task_class: str,
    days: int | None,
    score: float | None,
    eval_path: str | None,
    min_score: float | None,
    note: str,
    yes: bool,
):
    """Admit a local MODEL as good enough for TASK-CLASS (owned-capacity-first).

    Once admitted, `deepr expert sync`/`absorb` (without --local) run that task
    class on the local model automatically, draining owned capacity before any
    metered API call. Admission is your explicit acceptance: review local
    quality first (for example `deepr expert absorb ... --local --dry-run`)
    before admitting. Admissions expire (default 90 days) so they are re-earned
    as models change.

    EXAMPLES:
      deepr capacity admit llama3.1 --task-class sync
      deepr capacity admit qwen2.5:14b --task-class absorb --days 60 --score 0.74
      deepr capacity admit --from-eval data/benchmarks/local_compare_20260618_120000.json --task-class sync
    """
    from deepr.backends.admission import (
        DEFAULT_ADMISSION_DAYS,
        DEFAULT_LOCAL_EVAL_MIN_SCORE,
        AdmissionEvidenceError,
        load_local_eval_evidence,
        record_admission,
        resolve_local_eval_artifact,
    )

    if not model and eval_path is None:
        raise click.ClickException("MODEL is required unless --from-eval is provided.")
    if eval_path is None and min_score is not None:
        raise click.ClickException("--min-score is only used with --from-eval.")
    if eval_path is not None and score is not None:
        raise click.ClickException("--score is read from --from-eval; omit --score.")

    if eval_path is not None:
        threshold = min_score if min_score is not None else DEFAULT_LOCAL_EVAL_MIN_SCORE
        try:
            artifact_path = resolve_local_eval_artifact(eval_path)
            evidence = load_local_eval_evidence(artifact_path, model=model, min_score=threshold)
        except AdmissionEvidenceError as exc:
            raise click.ClickException(str(exc)) from exc
        model = evidence.model
        score = evidence.score
        note = f"{evidence.note()}; {note}" if note else evidence.note()

    lifetime = days if days is not None else DEFAULT_ADMISSION_DAYS
    if not yes:
        if not click.confirm(
            f"Admit local model '{model}' for '{task_class}' for {lifetime} days? "
            f"(sync/absorb will use it automatically)",
            default=False,
        ):
            click.echo("Cancelled.")
            return

    if model is None:
        raise click.ClickException("MODEL is required unless --from-eval is provided.")
    adm = record_admission(model, task_class, days=lifetime, score=score, note=note)
    exp = adm.expires_at.strftime("%Y-%m-%d") if adm.expires_at else "never"
    click.echo(f"Admitted '{model}' for '{task_class}' until {exp}.")
    click.echo(f"`deepr expert {task_class} ...` will now prefer this local model at $0 over metered API.")


@capacity.command(name="admissions")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def capacity_admissions(json_output: bool):
    """List local-model admissions currently in effect."""
    from deepr.backends.admission import list_active

    admitted = list_active()
    if json_output:
        click.echo(_json.dumps([a.to_dict() for a in admitted], indent=2))
        return
    if not admitted:
        click.echo("No active admissions. Admit one: deepr capacity admit <model> --task-class sync")
        return
    click.echo("Active local-model admissions:")
    for a in admitted:
        exp = a.expires_at.strftime("%Y-%m-%d") if a.expires_at else "never"
        score = f", score {a.score:.2f}" if a.score is not None else ""
        note = f" - {a.note}" if a.note else ""
        click.echo(f"  {a.model:24s} {a.task_class:10s} expires {exp}{score}{note}")


@capacity.command(name="revoke")
@click.argument("model")
@click.option("--task-class", "task_class", required=True, help="Task class to revoke admission for.")
def capacity_revoke(model: str, task_class: str):
    """Revoke MODEL's admission for TASK-CLASS (effective immediately)."""
    from deepr.backends.admission import is_admitted, revoke_admission

    if not is_admitted(model, task_class):
        click.echo(f"No active admission for '{model}' on '{task_class}'. Nothing to revoke.")
        return
    revoke_admission(model, task_class)
    click.echo(f"Revoked admission for '{model}' on '{task_class}'. Maintenance falls back to metered API.")
