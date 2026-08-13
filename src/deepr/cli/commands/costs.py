"""Cost tracking CLI commands.

Provides commands for viewing and managing costs:
- deepr costs show - Show cost summary
- deepr costs history - Show daily history
- deepr costs breakdown - Show breakdown by provider/operation/model
- deepr costs timeline - Show cost trends with ASCII chart
- deepr costs alerts - Show active alerts
- deepr costs expert - Show per-expert cost breakdown
"""

import json
from datetime import UTC
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from deepr.cli.commands.costs_spend_dispositions import (
    disposition_log_path_for_ledger,
    register_spend_disposition_commands,
)
from deepr.cli.commands.provider_billing import reconcile_billing_command
from deepr.observability.cost_ledger import CostLedger
from deepr.observability.costs import CostDashboard

console = Console()

SPEND_DECISIONS_SCHEMA_VERSION = "deepr-cost-spend-decisions-v1"
SPEND_DECISIONS_KIND = "deepr.costs.spend_decisions"


def _current_cost_authority(
    *,
    daily_display_limit: float | None = None,
    monthly_display_limit: float | None = None,
) -> dict[str, Any]:
    """Return strict settled spend, active holds, and effective authority."""
    from deepr.core.cost_caps import read_operator_budget_for_status, resolve_spend_caps, resolve_spend_policy
    from deepr.experts.research_reservation_store import ResearchReservationStore

    operator = read_operator_budget_for_status()
    policy = resolve_spend_policy()
    caps = resolve_spend_caps()
    daily_limit = float(caps["daily"])
    weekly_limit = float(caps["weekly"])
    monthly_limit = float(caps["monthly"])
    if daily_display_limit is not None:
        daily_limit = min(daily_limit, daily_display_limit)
    if monthly_display_limit is not None:
        monthly_limit = min(monthly_limit, monthly_display_limit)

    exposure = ResearchReservationStore().exposure_snapshot()
    active_holds = exposure.active_cost
    settled_since_wallet = 0.0
    if operator.spend_wallet_id:
        settled_since_wallet = exposure.total_settled_cost - operator.spend_wallet_settled_baseline_usd
        if settled_since_wallet < 0:
            raise ValueError("canonical settled cost is below the spend wallet baseline")
    daily_settled = exposure.daily_settled_cost
    weekly_settled = exposure.weekly_settled_cost
    monthly_settled = exposure.monthly_settled_cost
    if operator.spend_wallet_id:
        if "daily" not in policy.calendar_periods:
            daily_settled = settled_since_wallet
        if "weekly" not in policy.calendar_periods:
            weekly_settled = settled_since_wallet
        if "monthly" not in policy.calendar_periods:
            monthly_settled = settled_since_wallet
    daily_exposure = daily_settled + active_holds
    weekly_exposure = weekly_settled + active_holds
    monthly_exposure = monthly_settled + active_holds
    wallet_available = (
        max(0.0, operator.spend_wallet_authorized_usd - settled_since_wallet - active_holds)
        if operator.spend_wallet_id
        else float(caps["per_job"])
    )
    authorizable_headroom = max(
        0.0,
        min(
            float(caps["per_job"]),
            daily_limit - daily_exposure,
            weekly_limit - weekly_exposure,
            monthly_limit - monthly_exposure,
            wallet_available,
        ),
    )
    return {
        "per_job_limit": float(caps["per_job"]),
        "daily_limit": daily_limit,
        "weekly_limit": weekly_limit,
        "monthly_limit": monthly_limit,
        "daily_settled": daily_settled,
        "weekly_settled": weekly_settled,
        "monthly_settled": monthly_settled,
        "active_holds": active_holds,
        "unresolved_holds": exposure.unresolved_count,
        "unresolved_exposure": exposure.unresolved_cost,
        "daily_exposure": daily_exposure,
        "weekly_exposure": weekly_exposure,
        "monthly_exposure": monthly_exposure,
        "authorizable_headroom": authorizable_headroom,
        "authority_mode": "spend_wallet" if operator.spend_wallet_id else "provider_verified",
        "provider_hard_boundary_verified": operator.authorization_valid and not operator.frozen,
        "spend_wallet_authorized": operator.spend_wallet_authorized_usd,
        "spend_wallet_spent": settled_since_wallet,
        "spend_wallet_available": wallet_available if operator.spend_wallet_id else 0.0,
    }


def _threshold_label(exposure: float, limit: float) -> str | None:
    """Return the strongest live threshold crossed by current exposure."""
    if limit <= 0:
        return "paid API frozen at a $0.00 hard ceiling"
    utilization = exposure / limit
    if utilization >= 1:
        return "100% hard ceiling reached; paid API dispatch is blocked"
    if utilization >= 0.95:
        return "95% critical threshold reached"
    if utilization >= 0.80:
        return "80% warning threshold reached"
    if utilization >= 0.50:
        return "50% notice threshold reached"
    return None


def _utilization_display(exposure: float, limit: float) -> tuple[str, str]:
    """Render zero ceilings as frozen or breached, never as healthy utilization."""
    if limit <= 0:
        return ("OVER $0.00 CEILING", "red") if exposure > 0 else ("0.0%", "green")
    utilization = exposure / limit * 100
    color = "green" if utilization < 50 else "yellow" if utilization < 80 else "red"
    return f"{utilization:.1f}%", color


@click.group()
def costs():
    """Cost tracking and budget management."""
    pass


costs.add_command(reconcile_billing_command)
register_spend_disposition_commands(costs)


@costs.command()
@click.argument("prompt")
@click.option(
    "--model",
    "-m",
    default="o4-mini-deep-research",
    type=click.Choice(["o4-mini-deep-research", "o3-deep-research"]),
    help="Research model",
)
@click.option("--web-search/--no-web-search", default=True, help="Enable web search")
def estimate(prompt: str, model: str, web_search: bool):
    """Estimate the cost of a research prompt before running it.

    Example:
        deepr costs estimate "What are AI trends?"
        deepr costs estimate "Kubernetes guide" --model o3-deep-research
    """
    from deepr.core.costs import CostEstimator

    try:
        est = CostEstimator.estimate_cost(prompt=prompt, model=model, enable_web_search=web_search)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise click.Abort() from e

    console.print(
        Panel(
            f"Expected: [bold]${est.expected_cost:.2f}[/bold]\n"
            f"Min: ${est.min_cost:.2f}    Max: ${est.max_cost:.2f}\n\n"
            f"Model: {model}\n"
            f"Web search: {'enabled' if web_search else 'disabled'}\n"
            f"Prompt length: {len(prompt)} chars",
            title="Cost Estimate",
        )
    )


@costs.command()
@click.option(
    "--daily-limit",
    type=click.FloatRange(min=0.0, min_open=True),
    help="Narrow this display only; cannot raise effective daily authority",
)
@click.option(
    "--monthly-limit",
    type=click.FloatRange(min=0.0, min_open=True),
    help="Narrow this display only; cannot raise effective monthly authority",
)
def show(daily_limit: float | None, monthly_limit: float | None):
    """Show canonical settled spend, holds, and effective hard ceilings."""
    try:
        summary = _current_cost_authority(
            daily_display_limit=daily_limit,
            monthly_display_limit=monthly_limit,
        )
    except Exception as exc:
        raise click.ClickException("Canonical money state is unreadable; cost summary is unavailable.") from exc

    if summary.get("authority_mode") == "spend_wallet":
        wallet_exposure = summary["spend_wallet_spent"] + summary["active_holds"]
        utilization, color = _utilization_display(wallet_exposure, summary["spend_wallet_authorized"])
        monthly_remaining = max(0.0, summary["monthly_limit"] - summary["monthly_exposure"])
        console.print(
            Panel(
                f"[bold]Deepr metered-spend wallet[/bold]\n"
                f"Authorized credits: [bold]${summary['spend_wallet_authorized']:.2f}[/bold]\n"
                f"Settled from wallet: [bold]${summary['spend_wallet_spent']:.2f}[/bold]\n"
                f"Active holds: ${summary['active_holds']:.2f}\n"
                f"Unresolved post-dispatch holds: {int(summary['unresolved_holds'])} "
                f"(${summary['unresolved_exposure']:.2f})\n"
                f"Wallet drawdown: [bold]${wallet_exposure:.2f}[/bold] / "
                f"${summary['spend_wallet_authorized']:.2f}\n"
                f"Wallet available: ${summary['spend_wallet_available']:.2f}\n"
                f"Wallet utilization: [{color}]{utilization}[/{color}]\n"
                f"Effective monthly exposure: ${summary['monthly_exposure']:.2f} / "
                f"${summary['monthly_limit']:.2f}\n"
                f"Monthly headroom: ${monthly_remaining:.2f}\n"
                f"Maximum new paid call: ${summary['authorizable_headroom']:.2f}\n"
                f"Provider hard boundary: "
                f"{'verified' if summary['provider_hard_boundary_verified'] else 'not verified; paid API blocked'}\n"
                "\nLocal and verified plan-quota work records $0 and does not draw down this wallet. "
                "The wallet cannot replace provider prepaid-no-overage or a hard provider ceiling.",
                title="API Wallet Costs",
            )
        )
        console.print(
            f"[bold]Maximum currently authorizable new paid call:[/bold] ${summary['authorizable_headroom']:.2f}"
        )
        label = _threshold_label(wallet_exposure, summary["spend_wallet_authorized"])
        if label is not None:
            console.print(f"[bold red]Wallet alert:[/bold red] {label}")
        return

    # Daily summary
    daily_utilization, daily_color = _utilization_display(summary["daily_exposure"], summary["daily_limit"])
    daily_remaining = max(0.0, summary["daily_limit"] - summary["daily_exposure"])

    console.print(
        Panel(
            f"[bold]Today's Spending[/bold]\n"
            f"Settled: [bold]${summary['daily_settled']:.2f}[/bold]\n"
            f"Active holds: ${summary['active_holds']:.2f}\n"
            f"Unresolved post-dispatch holds: {int(summary['unresolved_holds'])} "
            f"(${summary['unresolved_exposure']:.2f})\n"
            f"Exposure: [bold]${summary['daily_exposure']:.2f}[/bold] / ${summary['daily_limit']:.2f}\n"
            f"Daily window headroom: ${daily_remaining:.2f}\n"
            f"Utilization: [{daily_color}]{daily_utilization}[/{daily_color}]",
            title="Daily Costs",
        )
    )

    # Monthly summary
    monthly_utilization, monthly_color = _utilization_display(summary["monthly_exposure"], summary["monthly_limit"])
    monthly_remaining = max(0.0, summary["monthly_limit"] - summary["monthly_exposure"])

    console.print(
        Panel(
            f"[bold]This Month's Spending[/bold]\n"
            f"Settled: [bold]${summary['monthly_settled']:.2f}[/bold]\n"
            f"Active holds: ${summary['active_holds']:.2f}\n"
            f"Exposure: [bold]${summary['monthly_exposure']:.2f}[/bold] / ${summary['monthly_limit']:.2f}\n"
            f"Monthly window headroom: ${monthly_remaining:.2f}\n"
            f"Utilization: [{monthly_color}]{monthly_utilization}[/{monthly_color}]",
            title="Monthly Costs",
        )
    )

    console.print(f"[bold]Maximum currently authorizable new paid call:[/bold] ${summary['authorizable_headroom']:.2f}")

    for period in ("daily", "weekly", "monthly"):
        label = _threshold_label(summary[f"{period}_exposure"], summary[f"{period}_limit"])
        if label is not None:
            console.print(f"[bold red]{period.title()} alert:[/bold red] {label}")


@costs.command()
@click.option("--days", default=14, help="Number of days to show")
def history(days: int):
    """Show daily cost history."""
    dashboard = CostDashboard()
    hist = dashboard.get_daily_history(days)

    table = Table(title=f"Cost History (Last {days} Days)")
    table.add_column("Date", style="cyan")
    table.add_column("Total", justify="right")
    table.add_column("Limit", justify="right")
    table.add_column("Utilization", justify="right")

    for day in hist:
        util_pct = day["utilization"] * 100
        util_color = "green" if util_pct < 50 else "yellow" if util_pct < 80 else "red"

        table.add_row(
            day["date"], f"${day['total']:.2f}", f"${day['limit']:.2f}", f"[{util_color}]{util_pct:.1f}%[/{util_color}]"
        )

    console.print(table)


@costs.command()
@click.option("--by", type=click.Choice(["provider", "operation", "model"]), default="provider")
@click.option(
    "--period", type=click.Choice(["today", "week", "month", "all"]), default="month", help="Time period to include"
)
def breakdown(by: str, period: str):
    """Show cost breakdown."""
    from datetime import datetime, timedelta

    dashboard = CostDashboard()

    period_labels = {"today": "Today", "week": "Last 7 Days", "month": "Last 30 Days", "all": "All Time"}

    if period == "today":
        start_date = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start_date = datetime.now(UTC) - timedelta(days=7)
    elif period == "month":
        start_date = datetime.now(UTC) - timedelta(days=30)
    else:
        start_date = None

    if by == "provider":
        data = dashboard.get_breakdown_by_provider(start_date=start_date)
        title = "Cost Breakdown by Provider"
    elif by == "operation":
        data = dashboard.get_breakdown_by_operation(start_date=start_date)
        title = "Cost Breakdown by Operation"
    else:
        data = dashboard.get_breakdown_by_model(start_date=start_date)
        title = "Cost Breakdown by Model"

    if not data:
        console.print(f"[dim]No cost data for {period_labels[period].lower()}[/dim]")
        return

    table = Table(title=f"{title} ({period_labels[period]})")
    table.add_column(by.title(), style="cyan")
    table.add_column("Cost", justify="right")
    table.add_column("Percentage", justify="right")

    total = sum(data.values())

    for name, cost in sorted(data.items(), key=lambda x: x[1], reverse=True):
        pct = (cost / total * 100) if total > 0 else 0
        table.add_row(name, f"${cost:.2f}", f"{pct:.1f}%")

    table.add_row("[bold]Total[/bold]", f"[bold]${total:.2f}[/bold]", "[bold]100%[/bold]")

    console.print(table)


@costs.command()
def alerts():
    """Show live cost thresholds from canonical settled spend and holds."""
    try:
        summary = _current_cost_authority()
    except Exception as exc:
        raise click.ClickException("Canonical money state is unreadable; paid dispatch remains blocked.") from exc

    active = []
    for period in ("daily", "weekly", "monthly"):
        exposure = summary[f"{period}_exposure"]
        limit = summary[f"{period}_limit"]
        label = _threshold_label(exposure, limit)
        if label is not None:
            active.append((period, exposure, limit, label))

    if not active:
        console.print("[green]OK No live cost thresholds crossed[/green]")
        return

    console.print(f"[bold red]Live Cost Alerts ({len(active)}):[/bold red]\n")
    for period, exposure, limit, label in active:
        console.print(
            Panel(
                f"[bold]{period.title()} Budget Alert[/bold]\n\n"
                f"Status: {label}\n"
                f"Settled plus active holds: ${exposure:.2f}\n"
                f"Effective hard ceiling: ${limit:.2f}",
                title="CURRENT EXPOSURE",
            )
        )


@costs.command()
@click.option("--daily", type=click.FloatRange(min=0.0), help="Unsupported legacy setter; use the named env cap")
@click.option("--monthly", type=click.FloatRange(min=0.0), help="Set the authoritative monthly paid API budget")
def limits(daily: float | None, monthly: float | None):
    """View effective caps or set the authoritative monthly budget."""
    if daily is not None:
        raise click.ClickException(
            "The legacy dashboard daily setter was not spend authority. Set DEEPR_MAX_COST_PER_DAY "
            "in the runtime environment, then restart Deepr and verify this command."
        )

    if monthly is not None:
        from deepr.cli.commands.budget import mutate_budget_config

        def update(config: dict[str, Any]) -> None:
            config["monthly_limit"] = monthly

        mutate_budget_config(update)
        console.print(f"[green]Authoritative monthly paid API budget set to ${monthly:.2f}[/green]")

    try:
        summary = _current_cost_authority()
    except Exception as exc:
        raise click.ClickException("Canonical money state is unreadable; paid dispatch remains blocked.") from exc

    from deepr.core.cost_caps import resolve_spend_caps

    caps = resolve_spend_caps()
    console.print(
        Panel(
            f"Per-job hard ceiling: ${caps['per_job']:.2f}\n"
            f"Daily hard ceiling: ${caps['daily']:.2f}\n"
            f"Weekly hard ceiling: ${caps['weekly']:.2f}\n"
            f"Monthly hard ceiling: ${caps['monthly']:.2f}\n\n"
            f"Monthly settled: ${summary['monthly_settled']:.2f}\n"
            f"Active durable holds: ${summary['active_holds']:.2f}\n"
            f"Monthly exposure: ${summary['monthly_exposure']:.2f}\n"
            f"Maximum authorizable new paid call: ${summary['authorizable_headroom']:.2f}\n"
            "Live thresholds: 50%, 80%, 95%, and 100%",
            title="Effective Cost Authority",
        )
    )


@costs.command()
@click.option("--days", default=30, help="Number of days to show")
@click.option("--weekly", is_flag=True, help="Aggregate by week instead of day")
def timeline(days: int, weekly: bool):
    """Show cost trends with ASCII chart."""
    dashboard = CostDashboard()
    hist = dashboard.get_daily_history(days)

    if not hist:
        console.print("[dim]No cost data available[/dim]")
        return

    if weekly:
        # Aggregate daily data into weekly buckets
        from collections import OrderedDict
        from datetime import date as date_type
        from datetime import timedelta

        weeks: dict = OrderedDict()
        for day in hist:
            d = date_type.fromisoformat(day["date"])
            week_start = d - timedelta(days=d.weekday())
            key = week_start.isoformat()
            if key not in weeks:
                weeks[key] = 0.0
            weeks[key] += day["total"]
        labels = list(weeks.keys())
        values = list(weeks.values())
        period_label = "Weekly"
    else:
        labels = [d["date"] for d in hist]
        values = [d["total"] for d in hist]
        period_label = "Daily"

    max_val = max(values) if values else 0
    avg_val = sum(values) / len(values) if values else 0
    anomaly_count = 0
    bar_width = 30

    table = Table(title=f"{period_label} Cost Timeline (Last {days} Days)")
    table.add_column("Date", style="cyan", no_wrap=True)
    table.add_column("Cost", justify="right", width=10)
    table.add_column("Chart", no_wrap=True)

    for label, val in zip(labels, values):
        bar_len = int((val / max_val) * bar_width) if max_val > 0 else 0
        is_anomaly = avg_val > 0 and val > 2 * avg_val

        if is_anomaly:
            color = "red"
            anomaly_count += 1
            prefix = "! "
        elif avg_val > 0 and val > avg_val:
            color = "yellow"
            prefix = "  "
        else:
            color = "green"
            prefix = "  "

        bar = "█" * bar_len
        table.add_row(f"{prefix}{label}", f"${val:.2f}", f"[{color}]{bar}[/{color}]")

    console.print(table)
    console.print(
        f"\n  Average: [bold]${avg_val:.2f}/{period_label.lower()[:-2]}y[/bold]"
        f"  |  Anomalies: [bold red]{anomaly_count}[/bold red] "
        f"{'days' if not weekly else 'weeks'} > 2x average"
    )


@costs.command("expert")
@click.argument("name")
def expert_costs(name: str):
    """Show cost breakdown for a specific expert."""
    from deepr.experts.profile import ExpertStore

    store = ExpertStore()
    profile = store.load(name)

    if profile is None:
        console.print(f"[red]Expert '{name}' not found[/red]")
        return

    # Expert summary
    budget_pct = (
        profile.monthly_spending / profile.monthly_learning_budget * 100 if profile.monthly_learning_budget > 0 else 0
    )
    budget_color = "green" if budget_pct < 50 else "yellow" if budget_pct < 80 else "red"

    console.print(
        Panel(
            f"[bold]Total Research Cost:[/bold] ${profile.total_research_cost:.2f}\n"
            f"[bold]Monthly Spending:[/bold] ${profile.monthly_spending:.2f} / "
            f"${profile.monthly_learning_budget:.2f}\n"
            f"[bold]Budget Used:[/bold] [{budget_color}]{budget_pct:.1f}%[/{budget_color}]\n"
            f"[bold]Research Runs:[/bold] {profile.research_triggered}\n"
            f"[bold]Conversations:[/bold] {profile.conversations}",
            title=f"Expert: {name}",
        )
    )

    # Per-operation breakdown from cost entries
    dashboard = CostDashboard()
    breakdown = dashboard.aggregator.get_expert_breakdown(name)

    if breakdown:
        table = Table(title="Cost by Operation Type")
        table.add_column("Operation", style="cyan")
        table.add_column("Cost", justify="right")

        total = sum(breakdown.values())
        for op, cost in sorted(breakdown.items(), key=lambda x: x[1], reverse=True):
            table.add_row(op, f"${cost:.2f}")
        table.add_row("[bold]Total[/bold]", f"[bold]${total:.2f}[/bold]")

        console.print(table)
    else:
        console.print("[dim]No detailed cost entries found for this expert[/dim]")


def _spend_decision_state(record: dict[str, Any]) -> str:
    decision = record.get("decision", {}) or {}
    return "allowed" if bool(decision.get("allowed", False)) else "deferred"


def _filter_spend_decisions(
    records: list[dict[str, Any]],
    *,
    expert: str | None,
    operation: str | None,
    decision: str,
    limit: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    expert_key = expert.casefold() if expert else None
    operation_key = operation.casefold() if operation else None

    for record in reversed(records):
        if expert_key and str(record.get("expert_name", "")).casefold() != expert_key:
            continue
        if operation_key and str(record.get("operation", "")).casefold() != operation_key:
            continue
        state = _spend_decision_state(record)
        if decision != "all" and state != decision:
            continue
        selected.append(record)
        if len(selected) >= limit:
            break
    return selected


def _spend_decisions_payload(
    records: list[dict[str, Any]],
    *,
    log_path: Path,
    expert: str | None,
    operation: str | None,
    decision: str,
    limit: int,
) -> dict[str, Any]:
    filtered = _filter_spend_decisions(
        records,
        expert=expert,
        operation=operation,
        decision=decision,
        limit=limit,
    )
    return {
        "schema_version": SPEND_DECISIONS_SCHEMA_VERSION,
        "kind": SPEND_DECISIONS_KIND,
        "contract": {
            "read_only": True,
            "cost_usd": 0.0,
            "source": "append_only_spend_decision_log",
            "stability": "experimental",
            "compatibility": {
                "additive_fields": True,
                "breaking_changes_require_new_schema_version": True,
                "deprecation_policy": "Fields in this v1 payload are additive within v1; removals use a new schema.",
            },
        },
        "log_path": str(log_path),
        "filters": {
            "expert": expert,
            "operation": operation,
            "decision": decision,
            "limit": limit,
        },
        "total_records": len(records),
        "count": len(filtered),
        "records": filtered,
    }


@costs.command("spend-decisions")
@click.option("--expert", help="Filter to one expert name.")
@click.option("--operation", help="Filter to one operation, for example expert_sync.")
@click.option(
    "--decision",
    type=click.Choice(["all", "allowed", "deferred"]),
    default="all",
    show_default=True,
    help="Filter by value-gate decision state.",
)
@click.option("--limit", type=int, default=20, show_default=True, help="Maximum decisions to show.")
@click.option("--json", "json_output", is_flag=True, help="Emit the versioned decision payload as JSON.")
def spend_decisions(expert: str | None, operation: str | None, decision: str, limit: int, json_output: bool):
    """Show value-of-spend gate decisions for metered operations."""
    if limit < 1:
        raise click.ClickException("--limit must be at least 1.")

    from deepr.experts.spend_decisions import load_spend_decisions, spend_decision_log_path

    log_path = spend_decision_log_path()
    records = load_spend_decisions(log_path)
    payload = _spend_decisions_payload(
        records,
        log_path=log_path,
        expert=expert,
        operation=operation,
        decision=decision,
        limit=limit,
    )

    if json_output:
        click.echo(json.dumps(payload, indent=2))
        return

    if not payload["records"]:
        console.print("[dim]No spend-decision records matched.[/dim]")
        console.print(f"[dim]Log: {log_path}[/dim]")
        return

    table = Table(title="Spend Decisions")
    table.add_column("Time", style="dim", no_wrap=True)
    table.add_column("Expert", style="cyan", min_width=12)
    table.add_column("Estimate", justify="right")
    table.add_column("Decision", justify="center", min_width=8)
    table.add_column("Reason")

    for record in payload["records"]:
        decision_data = record.get("decision", {}) or {}
        state = _spend_decision_state(record)
        style = "green" if state == "allowed" else "yellow"
        tier = str(decision_data.get("tier", "") or "")
        reason = str(decision_data.get("reason", "") or "")
        detail = f"{tier}: {reason}" if tier else reason
        table.add_row(
            str(record.get("timestamp", ""))[:19],
            str(record.get("expert_name", "")),
            f"${float(record.get('estimated_cost', 0.0) or 0.0):.4f}",
            f"[{style}]{state}[/{style}]",
            detail[:120],
        )

    console.print(table)


def _tracking_integrity_checks(dashboard, ledger, ledger_path: Path, drift_threshold: float):
    """Zero-cost integrity checks for the tracking stores themselves."""
    checks: list[tuple[str, bool, str]] = []

    # The dashboard file is a DERIVED view, regenerable from the canonical
    # ledger (via --rebuild), so its absence is not a problem - report it,
    # never fail on it. The ledger checks below are the real health (don't
    # cry wolf on a fresh/ledger-only setup).
    log_exists = dashboard.storage_path.exists()
    checks.append(
        (
            "Cost dashboard view",
            True,
            f"{dashboard.storage_path} ({'present' if log_exists else 'absent - regenerates from the ledger'})",
        )
    )

    # Ledger storage sanity
    health = ledger.get_health()
    write_path = str(health.get("primary_write_path") or health.get("path", ledger_path))
    read_paths = [str(path) for path in health.get("accounting_read_paths", [])]
    checks.append(("Ledger writable", bool(health.get("writable")), write_path))
    checks.append(
        (
            "Ledger accounting ready",
            bool(health.get("accounting_ready")),
            str(health.get("error") or f"write={write_path}; reads={', '.join(read_paths) or 'UNKNOWN'}"),
        )
    )
    source_details = "; ".join(
        f"{source.get('path')} ({int(source.get('event_count', 0))} events, "
        f"${float(source.get('total_cost_usd', 0.0)):.4f})"
        for source in health.get("accounting_sources", [])
    )
    checks.append(
        (
            "Accounting source coverage",
            bool(health.get("accounting_complete")) and bool(read_paths),
            source_details or str(health.get("error") or "UNKNOWN: no accounting roots resolved"),
        )
    )

    # Reconciliation drift check (dashboard is legacy mirror, ledger is canonical append-only)
    dashboard_total = sum(e.cost for e in dashboard.entries)
    try:
        ledger_total = ledger.with_locked_accounting_events(lambda events: sum(event.cost_usd for event in events))
    except Exception as exc:
        checks.append(
            (
                "Ledger vs dashboard drift",
                False,
                f"UNKNOWN: canonical ledger is unreadable ({exc})",
            )
        )
        return checks
    drift = abs(ledger_total - dashboard_total)
    checks.append(
        (
            "Ledger vs dashboard drift",
            drift <= drift_threshold,
            f"drift=${drift:.6f} (ledger=${ledger_total:.4f}, dashboard=${dashboard_total:.4f})",
        )
    )
    return checks


def _print_tracking_checks(checks) -> None:
    table = Table(title="Cost Tracking Doctor")
    table.add_column("Check", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Details")
    for name, ok, details in checks:
        table.add_row(name, "PASS" if ok else "FAIL", details)
    console.print(table)

    passed = sum(1 for _name, ok, _details in checks if ok)
    total = len(checks)
    if passed == total:
        console.print(f"[green]All checks passed ({passed}/{total})[/green]")
    else:
        console.print(f"[red]Issues found ({total - passed}/{total})[/red]")


def _doctor_classify(events, dir_names, cutoff, dispositions_by_key=None):
    """Split paid ledger events into matched, disposed, and unexplained.

    ``orphaned`` in legacy call sites means unexplained only: spend that still
    lacks both a report artifact and a durable disposition. Callers that need
    the three-way split should use ``classify_paid_events`` directly.
    """
    from deepr.observability.spend_dispositions import classify_paid_events

    matched, disposed, unexplained = classify_paid_events(
        events,
        dir_names,
        cutoff,
        dispositions_by_key=dispositions_by_key,
    )
    return matched, disposed, unexplained


@costs.command()
@click.option("--drift-threshold", default=0.01, type=float, show_default=True, help="Allowed absolute drift in USD")
@click.option(
    "--rebuild",
    is_flag=True,
    help="Rebuild the dashboard view from the canonical ledger before checking (repairs drift)",
)
@click.option("--days", default=45, show_default=True, help="How many days of ledger to reconcile")
@click.option("--reports-dir", default=None, help="Report root override (default: configured results_dir)")
@click.option("--ledger-path", default=None, hidden=True, help="Override ledger path (tests)")
@click.option("--json", "json_output", is_flag=True, help="Machine-readable output")
def doctor(
    drift_threshold: float,
    rebuild: bool,
    days: int,
    reports_dir: str | None,
    ledger_path: str | None,
    json_output: bool,
):
    """Cost-tracking integrity checks plus paid-artifact reconciliation.

    First audits the tracking stores themselves (ledger writable and
    accounting-ready, dashboard view drift vs the canonical ledger), then
    reconciles paid ledger events against report artifacts on disk. Settled
    dollars without a report must either carry a durable disposition
    (expected non-report, failed/cancelled, lost artifact, or unresolved
    provider evidence) or remain UNEXPLAINED. Exits 1 when unexplained spend
    remains, so schedulers and CI can alarm on it.
    """
    from datetime import datetime, timedelta

    from deepr.observability.spend_dispositions import latest_dispositions_by_event_key

    dashboard = (
        CostDashboard(storage_path=Path(ledger_path).with_name("cost_log.json")) if ledger_path else CostDashboard()
    )
    if rebuild:
        # The ledger is the append-only source of truth; the dashboard is a
        # derived view and may drift (several recorders write the ledger
        # directly). Regenerate the view rather than trusting it.
        count = dashboard.rebuild_from_ledger()
        if not json_output:
            console.print(f"[green]Rebuilt dashboard view from ledger ({count} entries)[/green]")
    ledger = CostLedger(ledger_path=Path(ledger_path)) if ledger_path else CostLedger()
    tracking_ledger_path = ledger.ledger_path
    tracking_checks = _tracking_integrity_checks(
        dashboard,
        ledger,
        tracking_ledger_path,
        drift_threshold,
    )

    from deepr.config import load_config

    root = Path(reports_dir) if reports_dir else Path(load_config()["results_dir"])
    dir_names = [d.name for d in root.iterdir() if d.is_dir()] if root.exists() else []
    cutoff = datetime.now(UTC) - timedelta(days=days)
    disp_path = disposition_log_path_for_ledger(ledger_path)
    try:
        events = ledger.with_locked_accounting_events(list)
    except Exception as exc:
        raise click.ClickException("Canonical cost ledger is unreadable; integrity status is UNKNOWN.") from exc
    matched, disposed, unexplained = _doctor_classify(
        events,
        dir_names,
        cutoff,
        dispositions_by_key=latest_dispositions_by_event_key(disp_path),
    )

    matched_total = sum(e["cost_usd"] for e in matched)
    disposed_total = sum(e["cost_usd"] for e in disposed)
    unexplained_total = sum(e["cost_usd"] for e in unexplained)
    # Backward-compatible alias: orphaned == still-unexplained only.
    orphaned_total = unexplained_total
    if json_output:
        payload = {
            "days": days,
            "matched_spend_usd": round(matched_total, 2),
            "disposed_spend_usd": round(disposed_total, 2),
            "unexplained_spend_usd": round(unexplained_total, 2),
            "orphaned_spend_usd": round(orphaned_total, 2),
            "matched": matched,
            "disposed": disposed,
            "unexplained": unexplained,
            "orphaned": unexplained,
            "tracking_checks": [{"name": name, "ok": ok, "details": details} for name, ok, details in tracking_checks],
        }
        click.echo(json.dumps(payload))
    else:
        _print_tracking_checks(tracking_checks)
        console.print(f"\n[bold]Cost doctor[/bold] (last {days} days)")
        console.print(
            f"  matched spend:     ${matched_total:.2f} across {len(matched)} event(s) with artifacts on disk"
        )
        console.print(
            f"  disposed spend:    ${disposed_total:.2f} across {len(disposed)} event(s) with durable dispositions"
        )
        colour = "red" if unexplained_total > 0.005 else "green"
        console.print(
            f"  [{colour}]unexplained spend: ${unexplained_total:.2f} across {len(unexplained)} event(s)[/{colour}]"
        )
        for entry in unexplained[:15]:
            console.print(
                f"    {entry['timestamp']}  ${entry['cost_usd']:6.2f}  "
                f"{entry.get('operation', '')}  {entry['provider']}/{entry['model']}",
                markup=False,
            )
        if len(unexplained) > 15:
            console.print(f"    ... and {len(unexplained) - 15} more")
        if unexplained_total > 0.005:
            console.print(
                "  Unexplained spend means money settled with no surviving report artifact "
                "and no durable disposition. Investigate with `deepr costs dispose-unexplained` "
                "or `deepr costs dispose` before it compounds."
            )
    if unexplained_total > 0.005 or not all(ok for _name, ok, _details in tracking_checks):
        raise SystemExit(1)
