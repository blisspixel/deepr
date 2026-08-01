"""CLI commands for durable spend dispositions (costs dispose family)."""

from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from deepr.observability.cost_ledger import CostLedger

console = Console()


def disposition_log_path_for_ledger(ledger_path: str | Path | None) -> Path | None:
    """Place the disposition log next to an overridden ledger path in tests."""
    if ledger_path is None:
        return None
    return Path(ledger_path).with_name("spend_dispositions.jsonl")


@click.command("dispositions")
@click.option("--limit", type=int, default=50, show_default=True, help="Maximum latest dispositions to show.")
@click.option("--json", "json_output", is_flag=True, help="Machine-readable output.")
@click.option("--ledger-path", default=None, hidden=True, help="Override ledger path (tests).")
def list_dispositions(limit: int, json_output: bool, ledger_path: str | None) -> None:
    """Show latest durable dispositions for non-report settled spend."""
    if limit < 1:
        raise click.ClickException("--limit must be at least 1.")
    from deepr.observability.spend_dispositions import (
        latest_dispositions_by_event_key,
        spend_disposition_log_path,
    )

    path = disposition_log_path_for_ledger(ledger_path)
    latest = latest_dispositions_by_event_key(path)
    records = sorted(latest.values(), key=lambda row: str(row.get("recorded_at") or ""), reverse=True)[:limit]
    log_path = spend_disposition_log_path(path)
    if json_output:
        click.echo(
            json.dumps(
                {
                    "path": str(log_path),
                    "count": len(latest),
                    "records": records,
                },
                indent=2,
            )
        )
        return
    if not records:
        console.print("[dim]No spend dispositions recorded.[/dim]")
        console.print(f"[dim]Log: {log_path}[/dim]")
        return
    table = Table(title="Spend Dispositions (latest per event)")
    table.add_column("Recorded", style="dim", no_wrap=True)
    table.add_column("Kind", style="cyan")
    table.add_column("Cost", justify="right")
    table.add_column("Operation")
    table.add_column("Task", max_width=28)
    for row in records:
        table.add_row(
            str(row.get("recorded_at", ""))[:19],
            str(row.get("disposition", "")),
            f"${float(row.get('cost_usd') or 0):.4f}",
            str(row.get("operation", "")),
            str(row.get("task_id", ""))[:28],
        )
    console.print(table)
    console.print(f"[dim]Log: {log_path} ({len(latest)} latest event keys)[/dim]")


@click.command("dispose")
@click.option(
    "--disposition",
    "disposition_kind",
    required=True,
    type=click.Choice(
        [
            "failed_or_cancelled",
            "expected_non_report",
            "lost_artifact",
            "unresolved_provider_evidence",
        ]
    ),
    help="Disposition kind for this settled event.",
)
@click.option("--event-key", required=True, help="Event identity key from costs doctor --json.")
@click.option("--cost-usd", type=float, required=True, help="Settled cost of the event.")
@click.option("--task-id", default="", help="Ledger task_id / job identity.")
@click.option("--operation", default="", help="Ledger operation name.")
@click.option("--provider", default="", help="Ledger provider.")
@click.option("--model", default="", help="Ledger model.")
@click.option("--event-timestamp", default="", help="Ledger event timestamp.")
@click.option("--request-id", default="", help="Provider request id when known.")
@click.option("--job-id", default="", help="Job identity when known.")
@click.option("--provider-receipt-id", default="", help="Provider receipt id when known.")
@click.option("--rationale", required=True, help="Human-readable reason for the disposition.")
@click.option("--json", "json_output", is_flag=True, help="Machine-readable output.")
@click.option("--ledger-path", default=None, hidden=True, help="Override ledger path (tests).")
def dispose_spend(
    disposition_kind: str,
    event_key: str,
    cost_usd: float,
    task_id: str,
    operation: str,
    provider: str,
    model: str,
    event_timestamp: str,
    request_id: str,
    job_id: str,
    provider_receipt_id: str,
    rationale: str,
    json_output: bool,
    ledger_path: str | None,
) -> None:
    """Record a durable disposition for one settled ledger event.

    Does not rewrite the append-only cost ledger. Does not authorize paid
    dispatch. Use after investigating unexplained spend from costs doctor.
    """
    from deepr.observability.spend_dispositions import record_spend_disposition

    record = record_spend_disposition(
        event_key=event_key,
        disposition=disposition_kind,
        cost_usd=cost_usd,
        task_id=task_id,
        operation=operation,
        provider=provider,
        model=model,
        event_timestamp=event_timestamp,
        rationale=rationale,
        request_id=request_id,
        job_id=job_id,
        provider_receipt_id=provider_receipt_id,
        path=disposition_log_path_for_ledger(ledger_path),
        recorded_by="operator",
    )
    if json_output:
        click.echo(json.dumps(record, indent=2))
        return
    console.print(
        f"[green]Recorded disposition[/green] {disposition_kind} for event {event_key[:48]} (${cost_usd:.4f})"
    )


@click.command("dispose-unexplained")
@click.option("--days", default=45, show_default=True, help="How many days of ledger to scan.")
@click.option("--reports-dir", default=None, help="Report root override (default: configured results_dir).")
@click.option("--ledger-path", default=None, hidden=True, help="Override ledger path (tests).")
@click.option(
    "--apply",
    is_flag=True,
    help="Write suggested dispositions. Without --apply, print a dry-run plan only.",
)
@click.option("--json", "json_output", is_flag=True, help="Machine-readable output.")
def dispose_unexplained(
    days: int,
    reports_dir: str | None,
    ledger_path: str | None,
    apply: bool,
    json_output: bool,
) -> None:
    """Suggest (and optionally apply) local dispositions for unexplained spend.

    Uses deterministic operation and identity rules only. Never calls a
    provider API and never rewrites the cost ledger.
    """
    from datetime import datetime, timedelta

    from deepr.config import load_config
    from deepr.observability.spend_dispositions import (
        apply_suggested_dispositions,
        classify_paid_events,
        latest_dispositions_by_event_key,
        suggest_disposition_for_orphan,
    )

    ledger = CostLedger(ledger_path=Path(ledger_path)) if ledger_path else CostLedger()
    disp_path = disposition_log_path_for_ledger(ledger_path)
    root = Path(reports_dir) if reports_dir else Path(load_config()["results_dir"])
    dir_names = [d.name for d in root.iterdir() if d.is_dir()] if root.exists() else []
    cutoff = datetime.now(UTC) - timedelta(days=days)
    try:
        events = ledger.with_locked_accounting_events(list)
    except Exception as exc:
        raise click.ClickException("Canonical cost ledger is unreadable; integrity status is UNKNOWN.") from exc
    _matched, _disposed, unexplained = classify_paid_events(
        events,
        dir_names,
        cutoff,
        dispositions_by_key=latest_dispositions_by_event_key(disp_path),
    )
    plan = []
    for entry in unexplained:
        kind, rationale, evidence = suggest_disposition_for_orphan(entry)
        plan.append(
            {
                **entry,
                "suggested_disposition": kind,
                "suggested_rationale": rationale,
                "evidence": evidence,
            }
        )
    written: list[dict[str, Any]] = []
    if apply and plan:
        written = apply_suggested_dispositions(unexplained, path=disp_path, recorded_by="forensic-auto")
    payload = {
        "days": days,
        "apply": apply,
        "unexplained_before": len(plan),
        "unexplained_spend_usd": round(sum(float(row["cost_usd"]) for row in plan), 4),
        "written": len(written),
        "plan": plan,
    }
    if json_output:
        click.echo(json.dumps(payload, indent=2))
        return
    console.print(f"[bold]Dispose unexplained[/bold] (last {days} days)")
    console.print(f"  unexplained events: {len(plan)} (${payload['unexplained_spend_usd']:.4f})")
    for row in plan[:20]:
        console.print(
            f"    {row['suggested_disposition']:24} ${float(row['cost_usd']):6.4f}  "
            f"{row.get('operation', '')}  {str(row.get('task_id', ''))[:36]}",
            markup=False,
        )
    if len(plan) > 20:
        console.print(f"    ... and {len(plan) - 20} more")
    if apply:
        console.print(f"[green]Wrote {len(written)} disposition record(s)[/green]")
    else:
        console.print("[dim]Dry run only. Re-run with --apply to record dispositions.[/dim]")


@click.command("parent-budget")
@click.option("--run-id", default=None, help="Replay one run id from the durable journal.")
@click.option("--limit", type=int, default=20, show_default=True, help="Max journal events to show.")
@click.option("--json", "json_output", is_flag=True, help="Machine-readable output.")
@click.option("--ledger-path", default=None, hidden=True, help="Override journal path (tests).")
def parent_budget_command(
    run_id: str | None,
    limit: int,
    json_output: bool,
    ledger_path: str | None,
) -> None:
    """Inspect durable parent budget transaction journal events."""
    if limit < 1:
        raise click.ClickException("--limit must be at least 1.")
    from deepr.experts.parent_budget_store import (
        load_parent_budget_events,
        parent_budget_log_path,
        replay_parent_budget,
    )

    journal = (
        Path(ledger_path).with_name("parent_budget_transactions.jsonl") if ledger_path else parent_budget_log_path()
    )
    if run_id:
        rebuilt = replay_parent_budget(run_id, journal)
        payload = {
            "path": str(journal),
            "run_id": run_id,
            "found": rebuilt is not None,
            "transaction": None if rebuilt is None else rebuilt.to_dict(),
        }
        if json_output:
            click.echo(json.dumps(payload, indent=2))
            return
        if rebuilt is None:
            console.print(f"[yellow]No parent budget run {run_id!r}[/yellow]")
            return
        console.print_json(data=payload["transaction"])
        return

    events = load_parent_budget_events(journal)
    tail = events[-limit:]
    payload = {
        "path": str(journal),
        "count": len(events),
        "events": tail,
    }
    if json_output:
        click.echo(json.dumps(payload, indent=2))
        return
    if not events:
        console.print("[dim]No parent budget journal events.[/dim]")
        console.print(f"[dim]Log: {payload['path']}[/dim]")
        return
    table = Table(title="Parent Budget Journal (latest)")
    table.add_column("Time", style="dim", no_wrap=True)
    table.add_column("Event")
    table.add_column("Run", max_width=20)
    table.add_column("Surface / child", max_width=28)
    for event in tail:
        table.add_row(
            str(event.get("recorded_at", ""))[:19],
            str(event.get("event_type", "")),
            str(event.get("run_id", ""))[:20],
            str(event.get("surface") or event.get("child_id") or event.get("operation") or "")[:28],
        )
    console.print(table)
    console.print(f"[dim]Log: {payload['path']} ({len(events)} events)[/dim]")


def register_spend_disposition_commands(group: click.Group) -> None:
    """Attach disposition commands to the costs group."""
    group.add_command(list_dispositions)
    group.add_command(dispose_spend)
    group.add_command(dispose_unexplained)
    group.add_command(parent_budget_command)
