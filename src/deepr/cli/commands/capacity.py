"""Show read-only local, plan-quota, and metered research capacity.

Design: docs/design/capacity-waterfall.md.
"""

from __future__ import annotations

import asyncio
import json as _json
import os
import shutil
from typing import Any

import click

from deepr.backends.capacity import BackendKind, CostModel, detect_capacity
from deepr.backends.local_capacity import LocalCapacityObservation, probe_local_gpu_occupancy
from deepr.backends.quota_ledger import QuotaState, summarize_quota_state
from deepr.cli.commands.capacity_validation import (
    FLEET_VALIDATION_DEFAULT_TIMEOUT_S,
    build_fleet_validation_payload,
    emit_fleet_validation_payload,
)

_PLAN_BACKEND_IDS = ("codex", "claude", "opencode", "kiro", "grok", "antigravity", "copilot")
_AUTO_PLAN_TASK_CLASSES = ("sync", "absorb", "gap_fill", "reflect")
_FLEET_PROBE_SCHEMA_VERSION = "deepr-plan-fleet-probe-v1"
_FLEET_PROBE_KIND = "deepr.capacity.probe_fleet"
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
    metered API call. The default view spends nothing; --probe does one tiny $0
    local round-trip. Manage automatic local maintenance with admit, admissions,
    and revoke.
    """
    # Group with a default action: only run the status view when no subcommand
    # was given (e.g. `deepr capacity admit ...` skips this body).
    if ctx.invoked_subcommand is not None:
        return

    sources = detect_capacity()
    quota_states = summarize_quota_state()
    local_capacity = probe_local_gpu_occupancy()

    local_probe = _run_local_probe() if probe else None
    if probe and not json_output and local_probe is not None:
        _print_local_probe(local_probe)

    if json_output:
        click.echo(
            _json.dumps(
                [
                    _source_to_dict(
                        s,
                        quota_states,
                        local_probe=local_probe,
                        local_capacity=local_capacity,
                    )
                    for s in sources
                ],
                indent=2,
            )
        )
        return

    _print_sources(sources)
    _print_local_capacity(local_capacity)
    _print_quota_summary(quota_states)
    _print_admissions_summary()


def _source_to_dict(
    source,
    quota_states: list[QuotaState],
    *,
    local_probe: dict[str, object] | None = None,
    local_capacity: LocalCapacityObservation | None = None,
) -> dict[str, object]:
    d = source.to_dict()
    states = _quota_states_for(source.backend_id, quota_states)
    state = _primary_quota_state(states)
    d["quota_state"] = state.to_dict() if state else None
    d["quota_states"] = [s.to_dict() for s in states]
    if local_probe is not None and source.kind == BackendKind.LOCAL:
        d["local_probe"] = local_probe
    if local_capacity is not None and source.kind == BackendKind.LOCAL:
        d["local_capacity"] = local_capacity.to_dict()
    return d


def _quota_states_for(backend_id: str, quota_states: list[QuotaState]) -> list[QuotaState]:
    if not backend_id:
        return []
    return [state for state in quota_states if state.backend_id == backend_id]


def _primary_quota_state(quota_states: list[QuotaState]) -> QuotaState | None:
    if not quota_states:
        return None
    # Account-scoped metadata probes can be newer and more authoritative than
    # an older backend-wide transport observation. The singular compatibility
    # field must not report stale exhaustion while ``quota_states`` contains a
    # fresh active account snapshot (or the inverse).
    return max(quota_states, key=lambda state: state.latest_event.timestamp)


def _run_local_probe() -> dict[str, object]:
    """One $0 round-trip to the local model."""
    from deepr.backends.local import probe_local
    from deepr.cli.async_runner import run_async_command

    return run_async_command(probe_local())


def _print_local_probe(result: dict[str, object]) -> None:
    """Print a human-readable local probe verdict."""
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

    local_or_plan = [
        s
        for s in sources
        if s.kind in (BackendKind.LOCAL, BackendKind.PLAN_QUOTA) and s.cost_model != CostModel.METERED and s.available
    ]
    if local_or_plan:
        names = ", ".join(s.name for s in local_or_plan)
        click.echo(f"Owned/prepaid capacity available: {names}")
    else:
        click.echo(
            "No owned/prepaid capacity detected. Install Ollama or a plan CLI to research without per-call cost."
        )
    click.echo("Note: CLI 'available' means installed on PATH only - auth, quota window, and overflow")
    click.echo("state are verified by the adapter at run time. Only the local probe (--probe) round-trips.")


def _print_local_capacity(observation: LocalCapacityObservation) -> None:
    click.echo("")
    click.echo(f"Local GPU capacity: {observation.state.value} - {observation.detail}")


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
    """List models/CLIs admitted for the automatic owned-capacity-first path."""
    from deepr.backends.admission import list_active
    from deepr.backends.waterfall import PLAN_ADMISSION_PREFIX

    admitted = list_active()
    local = [a for a in admitted if not a.model.startswith(PLAN_ADMISSION_PREFIX)]
    plan = [a for a in admitted if a.model.startswith(PLAN_ADMISSION_PREFIX)]

    click.echo("")
    if local:
        click.echo("Local models admitted for automatic owned-capacity-first maintenance:")
        for a in local:
            exp = a.expires_at.strftime("%Y-%m-%d") if a.expires_at else "never"
            click.echo(f"  [+] {a.model} for {a.task_class} (expires {exp})")
    else:
        click.echo("No local models admitted yet. `deepr capacity admit <model> --task-class sync` lets")
        click.echo("`expert sync`/`absorb` use a local model automatically (review quality first).")

    if plan:
        click.echo("")
        click.echo("Plan-quota CLIs with recorded routing intent (quota observation still required):")
        for a in plan:
            exp = a.expires_at.strftime("%Y-%m-%d") if a.expires_at else "never"
            click.echo(f"  [+] {a.model.removeprefix(PLAN_ADMISSION_PREFIX)} for {a.task_class} (expires {exp})")


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
@click.option("--probe", is_flag=True, help="Run a $0 live local probe before reporting local readiness.")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def capacity_next(
    task_class: str,
    expert_name: str,
    report_id: str,
    context_mode: str,
    scheduled: bool,
    probe: bool,
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

    local_probe = None
    local_capacity = probe_local_gpu_occupancy()
    try:
        job_context = CapacityJobContext(
            task_class=task_class,
            expert_name=expert_name,
            report_id=report_id,
            context_mode=context_mode,
            scheduled=scheduled,
        )
        local_probe = _run_local_probe() if probe else None
        actions = build_capacity_next_actions(
            task_class=task_class,
            job_context=job_context,
            local_probe=local_probe,
            local_capacity=local_capacity,
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    if json_output:
        payload = build_capacity_next_payload(
            job_context,
            actions,
            local_probe=local_probe,
            local_capacity=local_capacity,
        )
        click.echo(_json.dumps(payload, indent=2))
        return

    click.echo(f"Capacity next actions for task class: {task_class}\n")
    _print_local_capacity(local_capacity)
    if local_probe is not None:
        _print_local_probe(local_probe)
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
      deepr capacity admit --from-eval <benchmarks-dir>/local_compare_20260618_120000.json --task-class sync
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


@capacity.command(name="fleet")
@click.option("--json", "json_output", is_flag=True, help="Emit the versioned fleet payload as JSON.")
def capacity_fleet(json_output: bool):
    """Fleet status for every plan-quota CLI: installed, auth, routable, quota state.

    Read-only and $0: derived from PATH detection, the deterministic auth-mode
    gate, and the append-only quota ledger. "exhausted" with a reset time appears
    once a run has actually hit a vendor limit; "unobserved" means Deepr has not
    run that backend yet (vendors do not expose remaining quota up front).
    """
    from deepr.backends.plan_quota import build_fleet_payload, build_fleet_status

    rows = build_fleet_status()
    if json_output:
        click.echo(_json.dumps(build_fleet_payload(rows), indent=2))
        return

    click.echo("Plan-quota fleet (read-only, $0)\n")
    click.echo(f"{'backend':<12} {'installed':<10} {'auth':<8} {'routable':<9} {'status':<12} {'reset':<14} last seen")
    for r in rows:
        installed = "yes" if r["installed"] else "no"
        auth = r["auth_mode"] or "-"
        reset = _fmt_reset(r["reset_at"])
        last = (r["last_event_at"] or "-")[:16].replace("T", " ")
        click.echo(
            f"{r['backend']:<12} {installed:<10} {auth:<8} {r['routable']:<9} {r['status']:<12} {reset:<14} {last}"
        )
    click.echo("\nauto = waterfall may auto-route; explicit = --plan only; metered = paid per use (off by default)")


@capacity.command(name="refresh-quota")
@click.argument("backend", type=click.Choice(["codex", "claude", "grok"]))
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def capacity_refresh_quota(backend: str, json_output: bool):
    """Refresh trusted plan-quota metadata and record a quota-ledger event.

    Metadata-only and $0: reads a provider quota source such as Codex rollout
    logs or Claude Code's read-only usage endpoint, normalizes the binding
    window, and writes the local append-only quota ledger. It does not run a
    model call.
    """
    import sys

    from deepr.backends.plan_quota import collect_plan_quota_snapshot
    from deepr.backends.quota_ledger import QuotaLedger
    from deepr.backends.quota_snapshot import snapshot_availability, snapshot_to_ledger_event

    snapshot = collect_plan_quota_snapshot(backend)
    event = QuotaLedger().record_event(snapshot_to_ledger_event(snapshot))
    availability = snapshot_availability(snapshot, now=event.timestamp)
    payload = _quota_refresh_payload(snapshot, event, availability)
    success = snapshot.ok and availability.binding_window is not None

    if json_output:
        click.echo(_json.dumps(payload, indent=2))
        if not success:
            sys.exit(1)
        return

    if not success:
        detail = snapshot.error or availability.reason
        click.echo(f"{snapshot.display_name} quota snapshot unavailable: {detail}")
        sys.exit(1)

    headroom = _format_headroom(payload["headroom_fraction"])
    reset = f", reset {payload['reset_at']}" if payload["reset_at"] else ""
    click.echo(
        f"{snapshot.display_name} quota snapshot recorded: {payload['binding_window']} binding window, "
        f"{headroom} headroom{reset}."
    )


def _quota_refresh_payload(snapshot, event, availability) -> dict[str, object]:
    window = availability.binding_window
    return {
        "schema_version": "deepr-plan-quota-refresh-v1",
        "kind": "deepr.capacity.quota_refresh",
        "backend": snapshot.backend_id,
        "display_name": snapshot.display_name,
        "ok": snapshot.ok,
        "error": snapshot.error,
        "account_id": snapshot.account_id,
        "plan": snapshot.plan,
        "stale": snapshot.stale,
        "headroom_fraction": availability.headroom_fraction,
        "binding_window": window.label if window else None,
        "reset_at": availability.reset_at.isoformat() if availability.reset_at else None,
        "ledger_event": event.to_dict(),
    }


def _format_headroom(headroom_fraction: float | None) -> str:
    if headroom_fraction is None:
        return "unknown"
    return f"{headroom_fraction * 100:.1f}%"


def _fmt_reset(reset_at_iso: str | None) -> str:
    if not reset_at_iso:
        return "-"
    from datetime import UTC, datetime

    try:
        reset_at = datetime.fromisoformat(reset_at_iso)
    except ValueError:
        return "-"
    delta = reset_at - datetime.now(UTC)
    mins = int(delta.total_seconds() // 60)
    if mins <= 0:
        return "due"
    return f"~{mins // 60}h{mins % 60:02d}m" if mins >= 60 else f"~{mins}m"


@capacity.command(name="probe-plan")
@click.argument(
    "backend",
    type=click.Choice(_PLAN_BACKEND_IDS),
)
@click.option("--model", default=None, help="Model to pass to the CLI (e.g. anthropic/claude-sonnet-5 for opencode).")
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Compatibility confirmation flag; it cannot authorize a metered-at-margin adapter.",
)
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def capacity_probe_plan(backend: str, model: str | None, yes: bool, json_output: bool):
    """Validate that a plan-quota CLI backend works: auth gate + one round-trip.

    Runs the deterministic no-surprise-bills / auth-mode gate, then a single tiny
    call through the vendor CLI. Marginal cost must be $0 on a subscription
    plan. Metered-at-margin adapters remain visible choices but fail closed
    until complete cost accounting exists; ``-y`` cannot override that gate.
    """
    import os
    import sys

    from deepr.backends.plan_quota import evaluate_plan_quota_safety, get_adapter, probe_plan_quota
    from deepr.cli.async_runner import run_async_command

    adapter = get_adapter(backend)
    if adapter is None:  # pragma: no cover - Choice already constrains values
        click.echo(f"Unknown plan-quota backend: {backend}", err=True)
        sys.exit(2)

    decision = evaluate_plan_quota_safety(adapter, env=dict(os.environ))
    if not decision.safe:
        if json_output:
            click.echo(
                _json.dumps(
                    {
                        "backend": backend,
                        "auth_mode": decision.auth_mode.value,
                        "ok": False,
                        "reply": "",
                        "latency_ms": 0,
                        "error": decision.reason,
                    },
                    indent=2,
                )
            )
        else:
            click.echo(f"Cannot probe {adapter.display_name}: {decision.reason}", err=True)
        sys.exit(2)
    if decision.requires_ack and not yes and not json_output:
        if not click.confirm(f"{adapter.display_name} bills per use. Run one probe call?", default=False):
            click.echo("Cancelled.")
            return
    if not json_output:
        click.echo(decision.reason)
    if adapter.tos_note and not json_output:
        click.echo(f"Note: {adapter.tos_note}")

    result = run_async_command(probe_plan_quota(adapter, model=model))
    _record_probe_plan_observation(adapter, result)

    if json_output:
        click.echo(_json.dumps({"backend": backend, "auth_mode": decision.auth_mode.value, **result}, indent=2))
        return
    if result["ok"]:
        click.echo(
            f"{adapter.display_name}: OK - replied {result['reply'][:60]!r} in {result['latency_ms']}ms "
            f"(auth: {decision.auth_mode.value})"
        )
    else:
        click.echo(f"{adapter.display_name}: FAILED - {result['error']}")
        sys.exit(1)


@capacity.command(name="probe-fleet")
@click.option(
    "--backend",
    "backends",
    multiple=True,
    type=click.Choice(_PLAN_BACKEND_IDS),
    help="Plan backend to probe. Repeatable. Defaults to installed auto-routable backends.",
)
@click.option(
    "--all",
    "all_backends",
    is_flag=True,
    help="Probe every installed non-metered plan backend, including explicit-only experimental CLIs.",
)
@click.option(
    "--include-metered",
    is_flag=True,
    help="Compatibility selector for metered adapters; execution stays blocked until cost accounting exists.",
)
@click.option("--concurrency", type=click.IntRange(1, len(_PLAN_BACKEND_IDS)), default=4, show_default=True)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Compatibility confirmation flag; it cannot authorize a metered-at-margin adapter.",
)
@click.option("--json", "json_output", is_flag=True, help="Emit the versioned probe payload as JSON.")
def capacity_probe_fleet(
    backends: tuple[str, ...],
    all_backends: bool,
    include_metered: bool,
    concurrency: int,
    yes: bool,
    json_output: bool,
):
    """Fan out tiny validation probes across plan-quota CLIs.

    This is an operator validation surface, not an auto-routing shortcut. It
    probes only selected plan CLIs, records quota observations from successful
    or exhausted probes. Metered-at-margin adapters fail before probe dispatch;
    the retained ``--include-metered`` and ``-y`` flags cannot authorize them.
    """
    import sys

    adapters = _resolve_fleet_probe_adapters(
        backends=backends,
        all_backends=all_backends,
        include_metered=include_metered,
    )
    payload = _fleet_probe_payload_for(adapters, include_metered=include_metered, concurrency=concurrency)
    _emit_fleet_probe_payload(payload, json_output=json_output)

    if payload["failed_count"] or payload["probed_count"] == 0:
        sys.exit(1)


@capacity.command(name="validate-fleet")
@click.option(
    "--backend",
    "backends",
    multiple=True,
    type=click.Choice(_PLAN_BACKEND_IDS),
    help="Plan backend to validate. Repeatable. Defaults to installed auto-routable backends.",
)
@click.option(
    "--all",
    "all_backends",
    is_flag=True,
    help="Validate every installed non-metered plan backend, including explicit-only experimental CLIs.",
)
@click.option("--expert", "experts", multiple=True, help="Expert to target for the consult contract probe.")
@click.option(
    "--question",
    default=None,
    help="Validation consult question. Defaults to a contract-focused prompt.",
)
@click.option("--plan-model", default=None, help="Optional model hint passed to each selected plan CLI.")
@click.option("--concurrency", type=click.IntRange(1, len(_PLAN_BACKEND_IDS)), default=4, show_default=True)
@click.option(
    "--timeout",
    "timeout_seconds",
    default=FLEET_VALIDATION_DEFAULT_TIMEOUT_S,
    show_default=True,
    type=click.FloatRange(min=0.1),
)
@click.option("--json", "json_output", is_flag=True, help="Emit the versioned validation payload as JSON.")
def capacity_validate_fleet(
    backends: tuple[str, ...],
    all_backends: bool,
    experts: tuple[str, ...],
    question: str | None,
    plan_model: str | None,
    concurrency: int,
    timeout_seconds: float,
    json_output: bool,
):
    """Validate selected plan CLIs end to end without metered fallback.

    This runs the transport probe first, records quota observations, then runs
    the no-metered MCP consult contract check only for backends whose transport
    succeeded. Selected backends that are missing, skipped, exhausted, or fail
    transport make the fleet unhealthy instead of disappearing from the report.
    """
    import sys

    adapters = _resolve_fleet_probe_adapters(backends=backends, all_backends=all_backends)
    transport = _fleet_probe_payload_for(adapters, include_metered=False, concurrency=concurrency)
    payload = build_fleet_validation_payload(
        adapters,
        transport=transport,
        experts=experts,
        question=question,
        plan_model=plan_model,
        concurrency=concurrency,
        timeout_seconds=timeout_seconds,
    )
    emit_fleet_validation_payload(payload, json_output=json_output)

    if not payload["summary"]["ok"]:
        sys.exit(1)


def _resolve_fleet_probe_adapters(
    *,
    backends: tuple[str, ...],
    all_backends: bool,
    include_metered: bool = False,
):
    from deepr.backends.plan_quota import all_adapters

    if backends and all_backends:
        raise click.ClickException("Use either --backend or --all, not both.")
    adapter_index = {adapter.backend_id: adapter for adapter in all_adapters()}
    if backends:
        return [adapter_index[backend] for backend in backends]
    if all_backends:
        return [
            adapter
            for adapter in adapter_index.values()
            if _fleet_probe_installed(adapter) and (include_metered or not adapter.metered_at_margin)
        ]
    return [
        adapter for adapter in adapter_index.values() if adapter.enabled_by_default and _fleet_probe_installed(adapter)
    ]


def _fleet_probe_payload_for(adapters, *, include_metered: bool, concurrency: int) -> dict[str, Any]:
    from deepr.cli.async_runner import run_async_command

    if not adapters:
        return _fleet_probe_payload([], concurrency=concurrency)
    return run_async_command(_run_fleet_probe(adapters, include_metered=include_metered, concurrency=concurrency))


def _emit_fleet_probe_payload(payload: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        click.echo(_json.dumps(payload, indent=2))
        return
    if payload["selected_count"] == 0:
        click.echo("No plan-quota backends selected for probing.")
        return
    _print_fleet_probe(payload)


def _fleet_probe_installed(adapter) -> bool:
    return shutil.which(adapter.exe) is not None


async def _run_fleet_probe(adapters, *, include_metered: bool, concurrency: int) -> dict[str, Any]:
    semaphore = asyncio.Semaphore(concurrency)
    env = dict(os.environ)

    async def run_one(adapter):
        async with semaphore:
            return await _probe_fleet_backend(adapter, env=env, include_metered=include_metered)

    results = await asyncio.gather(*(run_one(adapter) for adapter in adapters))
    return _fleet_probe_payload(results, concurrency=concurrency)


async def _probe_fleet_backend(adapter, *, env: dict[str, str], include_metered: bool) -> dict[str, Any]:
    from deepr.backends.plan_quota import detect_auth_mode, evaluate_plan_quota_safety, probe_plan_quota

    installed = _fleet_probe_installed(adapter)
    raw_auth_mode = detect_auth_mode(adapter, env).value if installed else None
    base: dict[str, Any] = {
        "backend": adapter.backend_id,
        "name": adapter.display_name,
        "exe": adapter.exe,
        "installed": installed,
        "experimental": adapter.experimental,
        "metered_at_margin": adapter.metered_at_margin,
        "raw_auth_mode": raw_auth_mode,
        "auth_mode": None,
        "skipped": False,
        "status": "pending",
        "ok": False,
        "reply": "",
        "latency_ms": 0,
        "error": "",
        "safety": None,
        "tos_note": adapter.tos_note,
    }
    if not installed:
        return {**base, "skipped": True, "status": "skipped", "error": "not installed on PATH"}

    decision = evaluate_plan_quota_safety(adapter, env=env)
    base["auth_mode"] = decision.auth_mode.value
    base["safety"] = decision.to_dict()
    if not decision.safe:
        return {**base, "status": "failed", "error": decision.reason}
    if decision.requires_ack and not include_metered:
        return {
            **base,
            "skipped": True,
            "status": "skipped",
            "error": "metered-at-margin backend skipped; pass --include-metered -y to probe",
        }
    result = await probe_plan_quota(adapter)
    _record_probe_plan_observation(adapter, result)
    status = "ok" if result.get("ok") is True else "failed"
    return {**base, **result, "skipped": False, "status": status}


def _fleet_probe_payload(results: list[dict[str, Any]], *, concurrency: int) -> dict[str, Any]:
    probed = [result for result in results if not result.get("skipped")]
    failed = [result for result in probed if not result.get("ok")]
    ok = [result for result in probed if result.get("ok")]
    skipped = [result for result in results if result.get("skipped")]
    return {
        "schema_version": _FLEET_PROBE_SCHEMA_VERSION,
        "kind": _FLEET_PROBE_KIND,
        "contract": {
            "read_only": False,
            "cost_usd": 0.0,
            "uses_plan_quota": True,
            "metered_backends_skipped_by_default": True,
            "metered_backends_blocked_without_cost_accounting": True,
            "quota_observations_recorded": True,
        },
        "concurrency": concurrency,
        "selected_count": len(results),
        "probed_count": len(probed),
        "ok_count": len(ok),
        "failed_count": len(failed),
        "skipped_count": len(skipped),
        "results": results,
    }


def _print_fleet_probe(payload: dict[str, Any]) -> None:
    click.echo("Plan-quota fleet probe\n")
    for result in payload["results"]:
        backend = result["backend"]
        if result["skipped"]:
            click.echo(f"[skip] {backend:12s} {result['error']}")
        elif result["ok"]:
            click.echo(f"[ok]   {backend:12s} replied {result['reply'][:60]!r} in {result['latency_ms']}ms")
        else:
            click.echo(f"[fail] {backend:12s} {result['error']}")
        if result.get("tos_note"):
            click.echo(f"       note: {result['tos_note']}")
    click.echo(
        f"\n{payload['ok_count']} ok, {payload['failed_count']} failed, "
        f"{payload['skipped_count']} skipped, {payload['probed_count']} probed"
    )


def _record_probe_plan_observation(adapter, result: dict[str, object]) -> None:
    """Record quota observations from explicit probe-plan calls."""
    from deepr.backends.quota_ledger import (
        QuotaConfidence,
        QuotaEventType,
        QuotaLedger,
        QuotaLedgerEvent,
    )

    # The real probe owns attempt accounting so direct library calls and CLI
    # calls have the same append-only behavior. Retain this compatibility path
    # for injected/legacy probe implementations that do not return the field.
    if "quota_observation_recorded" in result:
        return

    event_type = None
    detail = ""
    if result.get("ok") is True:
        event_type = QuotaEventType.USAGE_OBSERVED
        detail = "probe-plan successful plan call"
    elif result.get("error") == "quota exhausted":
        event_type = QuotaEventType.EXHAUSTED
        detail = "probe-plan exhaustion signature"
    if event_type is None:
        return

    QuotaLedger().record_event(
        QuotaLedgerEvent(
            backend_id=adapter.backend_id,
            event_type=event_type,
            cost_model=adapter.cost_model,
            window_kind=adapter.window_kind,
            units_used=1.0 if event_type == QuotaEventType.USAGE_OBSERVED else None,
            unit_name=adapter.unit_name,
            remaining_confidence=QuotaConfidence.UNKNOWN,
            overage_enabled=False,
            detail=detail,
        )
    )


@capacity.command(name="admit-plan")
@click.argument("backend", type=click.Choice(["codex", "claude", "opencode"]))
@click.option(
    "--task-class", "task_class", type=click.Choice(_AUTO_PLAN_TASK_CLASSES), default="sync", show_default=True
)
@click.option("--days", type=int, default=None, help="Admission lifetime in days (default 90).")
def capacity_admit_plan(backend: str, task_class: str, days: int | None):
    """Record operator intent for plan-quota routing on TASK-CLASS.

    Vendor CLIs do not expose remaining quota, so Deepr never auto-routes to one
    on a guess. This dated admission says draining your subscription window for
    background maintenance is intended, but auto-routing still needs a trusted
    remaining-quota observation. The deterministic auth-mode/no-surprise-bills
    gate still applies. Explicit `--plan <id>` remains available without
    admission.
    """
    import os
    import sys

    from deepr.backends.admission import DEFAULT_ADMISSION_DAYS, record_admission
    from deepr.backends.plan_quota import evaluate_plan_quota_safety, get_adapter
    from deepr.backends.waterfall import PLAN_ADMISSION_PREFIX

    adapter = get_adapter(backend)
    if adapter is None:  # pragma: no cover - Choice already constrains values
        click.echo(f"Unknown plan-quota backend: {backend}", err=True)
        sys.exit(2)

    decision = evaluate_plan_quota_safety(adapter, env=dict(os.environ))
    if not decision.safe:
        click.echo(f"Cannot admit {adapter.display_name}: {decision.reason}", err=True)
        sys.exit(2)
    click.echo(decision.reason)

    record_admission(
        f"{PLAN_ADMISSION_PREFIX}{backend}",
        task_class,
        days=days or DEFAULT_ADMISSION_DAYS,
        note=f"operator-attested plan routing intent for {adapter.display_name}",
    )
    click.echo(
        f"Recorded plan-routing intent for {adapter.display_name} on {task_class!r} maintenance.\n"
        "Auto-routing also requires a trusted remaining-quota observation; explicit --plan still works now.\n"
        f"Revoke: deepr capacity revoke-plan {backend} --task-class {task_class}"
    )


@capacity.command(name="revoke-plan")
@click.argument("backend", type=click.Choice(["codex", "claude", "opencode"]))
@click.option("--task-class", "task_class", type=click.Choice(_AUTO_PLAN_TASK_CLASSES), required=True)
def capacity_revoke_plan(backend: str, task_class: str):
    """Revoke a plan-quota backend's routing admission for TASK-CLASS."""
    from deepr.backends.admission import is_admitted, revoke_admission
    from deepr.backends.waterfall import PLAN_ADMISSION_PREFIX

    model = f"{PLAN_ADMISSION_PREFIX}{backend}"
    if not is_admitted(model, task_class):
        click.echo(f"No active plan admission for '{backend}' on '{task_class}'. Nothing to revoke.")
        return
    revoke_admission(model, task_class)
    click.echo(
        f"Revoked plan-routing intent for '{backend}' on '{task_class}'. It stays available via --plan {backend}."
    )
