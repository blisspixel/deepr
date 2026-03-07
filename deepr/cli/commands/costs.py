"""Cost tracking CLI commands.

Provides commands for viewing and managing costs:
- deepr costs show - Show cost summary
- deepr costs history - Show daily history
- deepr costs breakdown - Show breakdown by provider/operation/model
- deepr costs timeline - Show cost trends with ASCII chart
- deepr costs alerts - Show active alerts
- deepr costs expert - Show per-expert cost breakdown
"""

from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from deepr.observability.cost_ledger import CostLedger
from deepr.observability.costs import CostDashboard

console = Console()


@click.group()
def costs():
    """Cost tracking and budget management."""
    pass


@costs.command()
@click.option("--daily-limit", type=float, help="Daily spending limit")
@click.option("--monthly-limit", type=float, help="Monthly spending limit")
def show(daily_limit: Optional[float], monthly_limit: Optional[float]):
    """Show cost summary."""
    dashboard = CostDashboard(daily_limit=daily_limit or 10.0, monthly_limit=monthly_limit or 100.0)

    summary = dashboard.get_summary()

    # Daily summary
    daily = summary["daily"]
    daily_pct = daily["utilization"] * 100
    daily_color = "green" if daily_pct < 50 else "yellow" if daily_pct < 80 else "red"

    console.print(
        Panel(
            f"[bold]Today's Spending[/bold]\n"
            f"Total: [bold]${daily['total']:.2f}[/bold] / ${daily['limit']:.2f}\n"
            f"Remaining: ${daily['remaining']:.2f}\n"
            f"Utilization: [{daily_color}]{daily_pct:.1f}%[/{daily_color}]",
            title="Daily Costs",
        )
    )

    # Monthly summary
    monthly = summary["monthly"]
    monthly_pct = monthly["utilization"] * 100
    monthly_color = "green" if monthly_pct < 50 else "yellow" if monthly_pct < 80 else "red"

    console.print(
        Panel(
            f"[bold]This Month's Spending[/bold]\n"
            f"Total: [bold]${monthly['total']:.2f}[/bold] / ${monthly['limit']:.2f}\n"
            f"Remaining: ${monthly['remaining']:.2f}\n"
            f"Utilization: [{monthly_color}]{monthly_pct:.1f}%[/{monthly_color}]",
            title="Monthly Costs",
        )
    )

    # Active alerts
    if summary["active_alerts"]:
        console.print("\n[bold red]Active Alerts:[/bold red]")
        for alert in summary["active_alerts"]:
            level_color = "red" if alert["level"] == "critical" else "yellow"
            console.print(
                f"  [{level_color}]●[/{level_color}] "
                f"{alert['period'].title()}: {alert['threshold'] * 100:.0f}% threshold exceeded "
                f"(${alert['current_value']:.2f} / ${alert['limit']:.2f})"
            )


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
    from datetime import datetime, timedelta, timezone

    dashboard = CostDashboard()

    period_labels = {"today": "Today", "week": "Last 7 Days", "month": "Last 30 Days", "all": "All Time"}

    if period == "today":
        start_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start_date = datetime.now(timezone.utc) - timedelta(days=7)
    elif period == "month":
        start_date = datetime.now(timezone.utc) - timedelta(days=30)
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
    """Show active cost alerts."""
    dashboard = CostDashboard()
    active = dashboard.get_active_alerts()

    if not active:
        console.print("[green]✓ No active cost alerts[/green]")
        return

    console.print(f"[bold red]Active Alerts ({len(active)}):[/bold red]\n")

    for alert in active:
        level_color = "red" if alert.level == "critical" else "yellow"
        level_icon = "🔴" if alert.level == "critical" else "🟡"

        console.print(
            Panel(
                f"[bold]{alert.period.title()} Budget Alert[/bold]\n\n"
                f"Level: [{level_color}]{alert.level.upper()}[/{level_color}]\n"
                f"Threshold: {alert.threshold * 100:.0f}%\n"
                f"Current: ${alert.current_value:.2f}\n"
                f"Limit: ${alert.limit:.2f}\n"
                f"Triggered: {alert.triggered_at.strftime('%Y-%m-%d %H:%M')}",
                title=f"{level_icon} {alert.level.title()} Alert",
            )
        )


@costs.command()
@click.option("--daily", type=float, help="Set daily limit")
@click.option("--monthly", type=float, help="Set monthly limit")
def limits(daily: Optional[float], monthly: Optional[float]):
    """View or set cost limits."""
    dashboard = CostDashboard()

    if daily is None and monthly is None:
        # Show current limits
        console.print(
            Panel(
                f"Daily Limit: ${dashboard.daily_limit:.2f}\n"
                f"Monthly Limit: ${dashboard.monthly_limit:.2f}\n\n"
                f"Alert Thresholds: {', '.join(f'{t * 100:.0f}%' for t in dashboard.alert_thresholds)}",
                title="Current Cost Limits",
            )
        )
    else:
        # Update limits
        if daily is not None:
            dashboard.daily_limit = daily
            console.print(f"[green]✓ Daily limit set to ${daily:.2f}[/green]")

        if monthly is not None:
            dashboard.monthly_limit = monthly
            console.print(f"[green]✓ Monthly limit set to ${monthly:.2f}[/green]")


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


@costs.command("doctor")
@click.option("--drift-threshold", default=0.01, type=float, show_default=True, help="Allowed absolute drift in USD")
def costs_doctor(drift_threshold: float):
    """Run zero-cost integrity checks for cost tracking."""
    dashboard = CostDashboard()
    ledger_path = Path(dashboard.storage_path).with_name("cost_ledger.jsonl")
    ledger = CostLedger(ledger_path=ledger_path)

    checks: list[tuple[str, bool, str]] = []

    # Dashboard storage sanity
    log_exists = dashboard.storage_path.exists()
    checks.append(("Cost log exists", log_exists, str(dashboard.storage_path)))

    # Ledger storage sanity
    health = ledger.get_health()
    checks.append(("Ledger writable", bool(health.get("writable")), str(health.get("path", ledger_path))))

    # Reconciliation drift check (dashboard is legacy mirror, ledger is canonical append-only)
    dashboard_total = sum(e.cost for e in dashboard.entries)
    ledger_total = ledger.get_total_cost()
    drift = abs(ledger_total - dashboard_total)
    drift_ok = drift <= drift_threshold
    checks.append(
        (
            "Ledger vs dashboard drift",
            drift_ok,
            f"drift=${drift:.6f} (ledger=${ledger_total:.4f}, dashboard=${dashboard_total:.4f})",
        )
    )

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
