"""Budget management commands."""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path
from typing import Any

import click

from deepr.cli.colors import print_header
from deepr.core.cost_caps import (
    OperatorBudget,
    budget_file_path,
    parse_operator_budget,
    read_operator_budget,
    resolve_spend_caps,
    spend_policy_lock,
)


def get_budget_file() -> Path:
    """Get budget configuration file path."""
    return budget_file_path()


def _load_budget_config_unlocked() -> dict[str, Any]:
    budget_file = get_budget_file()
    if not budget_file.exists():
        return {
            "monthly_limit": 0,
            "paid_api_frozen": False,
            "freeze_reason": "",
            "current_month": datetime.now(UTC).strftime("%Y-%m"),
            "monthly_spending": 0.0,
            "history": [],
        }

    # Validate the spend-authority fields with the same strict parser used by
    # every reservation before loading display-only history and counters.
    read_operator_budget(budget_file)
    with open(budget_file, encoding="utf-8") as f:
        config = json.load(f)

    # Reset if new month
    current_month = datetime.now(UTC).strftime("%Y-%m")
    if config.get("current_month") != current_month:
        config["current_month"] = current_month
        config["monthly_spending"] = 0.0

    return config


def load_budget_config() -> dict[str, Any]:
    """Load budget configuration under the shared policy lock."""
    with spend_policy_lock(get_budget_file()):
        return _load_budget_config_unlocked()


def _save_budget_config_unlocked(config: dict[str, Any]) -> None:
    from deepr.utils.atomic_io import atomic_write_json

    parse_operator_budget(config)
    budget_file = get_budget_file()
    budget_file.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(budget_file, config, fsync=True)


def mutate_budget_config(mutator: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    """Apply one read-modify-write policy transaction to the latest state."""
    with spend_policy_lock(get_budget_file()):
        config = _load_budget_config_unlocked()
        mutator(config)
        _save_budget_config_unlocked(config)
        return config


def _ledger_month_spend() -> float | None:
    """Current calendar-month spend from the canonical cost ledger.

    The budget.json counter only sees spend recorded through
    record_spending; the ledger sees every recorder (CLI, web, MCP,
    expert learning). Budget decisions use whichever is HIGHER, so a
    path that bypassed the side counter cannot make the month look
    cheaper than it was. Returns None when the ledger cannot be read:
    an unreadable ledger must never look like $0 spent - that would
    UNLOCK spending exactly when the spend record is broken. Callers
    treat None as "cannot verify, require manual confirmation".
    """
    try:
        from deepr.observability.cost_ledger import CostLedger

        now = datetime.now(UTC)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return CostLedger().get_total_cost(start_date=month_start)
    except Exception:
        return None


def check_budget_approval(estimated_cost: float) -> bool:
    """
    Check if job should auto-execute based on budget.

    Returns:
        True if approved, False if needs manual confirmation
    """
    if isinstance(estimated_cost, bool) or not isinstance(estimated_cost, (int, float)):
        return False
    estimated_cost = float(estimated_cost)
    if not isfinite(estimated_cost) or estimated_cost < 0:
        return False

    try:
        config = load_budget_config()
        monthly_limit = resolve_spend_caps(operator_budget=parse_operator_budget(config))["monthly"]
    except Exception:
        return False

    ledger_spend = _ledger_month_spend()
    if monthly_limit <= 0 or ledger_spend is None:
        return False

    # Spend = max(side counter, canonical ledger) so
    # spend recorded by other entry points (web, MCP, expert learning)
    # counts against the month even if record_spending never saw it.
    current_spending = max(config.get("monthly_spending", 0.0), ledger_spend)
    # The durable reservation boundary enforces the absolute ceiling. Keep the
    # interactive auto-approval threshold deliberately lower so approaching a
    # hard cap still requires an explicit human decision.
    return current_spending + estimated_cost < monthly_limit * 0.8


def record_spending(cost: float, job_id: str, description: str):
    """Record spending in budget."""
    if isinstance(cost, bool) or not isinstance(cost, (int, float)):
        raise ValueError("cost must be a finite non-negative number")
    cost = float(cost)
    if not isfinite(cost) or cost < 0:
        raise ValueError("cost must be a finite non-negative number")

    def record(config: dict[str, Any]) -> None:
        config["monthly_spending"] = config.get("monthly_spending", 0.0) + cost
        history = config.setdefault("history", [])
        history.append(
            {"timestamp": datetime.now(UTC).isoformat(), "cost": cost, "job_id": job_id, "description": description}
        )
        config["history"] = history[-100:]

    mutate_budget_config(record)


def _budget_threshold_notice(percentage: float) -> str | None:
    """Return the strongest human-readable monthly threshold notice."""
    if percentage >= 100:
        return "Paid API blocked: monthly hard ceiling exceeded"
    if percentage >= 90:
        return "Warning: Budget nearly exhausted"
    if percentage >= 80:
        return "Note: Approaching budget limit"
    return None


@click.group()
def budget():
    """Manage monthly research budget."""
    pass


@budget.command()
@click.argument("amount", type=click.FloatRange(min=0.0))
def set(amount: float):
    """
    Set monthly research budget.

    Examples:
        deepr budget set 50      # $50/month budget
        deepr budget set 0       # Freeze paid API dispatch
    """
    print_header("Budget Configuration")

    def update(config: dict[str, Any]) -> None:
        config["monthly_limit"] = amount

    config = mutate_budget_config(update)

    if amount == 0:
        click.echo("\nBudget: Paid API dispatch frozen ($0 hard ceiling)")
    else:
        # Show the same reconciled number the approval gate uses. The session
        # counter alone once displayed $0.00 while the canonical ledger held
        # $37.99 of campaign spend - the display must never lie about money.
        ledger_spend = _ledger_month_spend()
        spent = max(float(config.get("monthly_spending", 0) or 0), ledger_spend or 0.0)
        effective_limit = resolve_spend_caps()["monthly"]
        click.echo(f"\nConfigured budget: ${amount:.2f}/month")
        click.echo(f"Effective hard ceiling: ${effective_limit:.2f}/month")
        click.echo(f"Current spending (ledger-reconciled): ${spent:.2f}")
        if ledger_spend is None:
            click.echo("Warning: the canonical cost ledger could not be read; real spend may be higher.")
        click.echo(f"Resets: {datetime.now(UTC).strftime('%B')} 1 UTC")


@budget.command()
def status():
    """Show current budget status."""
    print_header("Budget Status")

    config = load_budget_config()
    configured_monthly = float(config.get("monthly_limit", 0) or 0)
    effective_monthly = resolve_spend_caps(operator_budget=parse_operator_budget(config))["monthly"]
    # The approval gate spends against max(session counter, canonical ledger),
    # so the status display must show that same reconciled number. Showing only
    # the session counter once reported $0.00 while the ledger held $37.99 of
    # campaign spend recorded by other entry points - the exact blindfold that
    # let a surprise bill go unnoticed for 24 days.
    counter_spending = float(config.get("monthly_spending", 0.0) or 0.0)
    ledger_raw = _ledger_month_spend()
    ledger_unreadable = ledger_raw is None
    ledger_spending = ledger_raw or 0.0
    current_spending = max(counter_spending, ledger_spending)
    current_month = config.get("current_month", datetime.now(UTC).strftime("%Y-%m"))

    if config.get("paid_api_frozen", False):
        reason = str(config.get("freeze_reason", "") or "manual operator freeze")
        click.echo(f"\nMode: Paid API frozen ({reason})")
        click.echo(f"Configured monthly ceiling: ${configured_monthly:.2f}")
        click.echo("Effective monthly ceiling: $0.00")
    elif effective_monthly == 0:
        click.echo("\nMode: Paid API frozen ($0 hard ceiling)")
    else:
        percentage = current_spending / effective_monthly * 100
        remaining = max(0.0, effective_monthly - current_spending)
        overage = max(0.0, current_spending - effective_monthly)

        click.echo(f"\nBudget: ${current_spending:.2f} / ${effective_monthly:.2f} ({percentage:.0f}%)")
        if configured_monthly != effective_monthly:
            click.echo(f"Configured monthly budget: ${configured_monthly:.2f}; tighter policy is active")
        click.echo(f"Remaining: ${remaining:.2f}")
        if overage > 0:
            click.echo(f"Over hard ceiling by: ${overage:.2f}")
        if ledger_unreadable:
            click.echo(
                "Warning: the canonical cost ledger could not be read; real spend may be "
                "higher and metered auto-approval is disabled until it is readable."
            )
        if ledger_spending - counter_spending > 0.01:
            click.echo(
                f"Note: ${ledger_spending - counter_spending:.2f} of this month's spend was recorded "
                "by other entry points (ledger) and never hit the session counter. "
                "The ledger is canonical; run 'deepr costs doctor' to audit it."
            )

        threshold_notice = _budget_threshold_notice(percentage)
        if threshold_notice is not None:
            click.echo(f"\n{threshold_notice}")

    click.echo(f"\nCurrent month: {current_month}")

    # Next reset
    next_month = datetime.now(UTC).replace(day=1)
    if next_month.month == 12:
        next_month = next_month.replace(year=next_month.year + 1, month=1)
    else:
        next_month = next_month.replace(month=next_month.month + 1)
    click.echo(f"Resets: {next_month.strftime('%B %d, %Y')}")


@budget.command()
@click.option("--reason", default="manual operator freeze", show_default=True)
def freeze(reason: str) -> None:
    """Immediately block every paid API reservation."""
    print_header("Budget Freeze")

    def update(config: dict[str, Any]) -> None:
        config["paid_api_frozen"] = True
        config["freeze_reason"] = reason.strip() or "manual operator freeze"
        config["frozen_at"] = datetime.now(UTC).isoformat()

    mutate_budget_config(update)
    click.echo("\nPaid API dispatch is frozen. Local and safety-eligible plan capacity remain available.")


@budget.command()
def unfreeze() -> None:
    """Remove a manual freeze only when positive monthly headroom remains."""
    print_header("Budget Unfreeze")
    result: dict[str, float] = {}

    def update(config: dict[str, Any]) -> None:
        try:
            candidate = OperatorBudget(
                configured=True,
                monthly_limit=float(config.get("monthly_limit", 0.0)),
                frozen=False,
            )
            effective_limit = resolve_spend_caps(operator_budget=candidate)["monthly"]
        except (TypeError, ValueError) as exc:
            raise click.ClickException(str(exc)) from exc
        ledger_spend = _ledger_month_spend()
        if ledger_spend is None:
            raise click.ClickException("The canonical cost ledger is unreadable; paid dispatch remains frozen.")
        current_spending = max(float(config.get("monthly_spending", 0.0) or 0.0), ledger_spend)
        if effective_limit <= 0:
            raise click.ClickException("Set a positive finite monthly budget before unfreezing paid dispatch.")
        if current_spending >= effective_limit:
            raise click.ClickException(
                f"Current monthly spend ${current_spending:.2f} has exhausted the ${effective_limit:.2f} hard ceiling. "
                "Wait for the UTC month rollover or explicitly raise the ceiling before unfreezing."
            )
        config["paid_api_frozen"] = False
        config["freeze_reason"] = ""
        config.pop("frozen_at", None)
        result["headroom"] = effective_limit - current_spending

    mutate_budget_config(update)
    click.echo(f"\nPaid API dispatch unfrozen with ${result['headroom']:.2f} monthly headroom.")


@budget.command()
@click.option("--limit", "-n", default=10, help="Number of recent transactions to show")
def history(limit: int):
    """Show spending history."""
    print_header("Spending History")

    config = load_budget_config()
    history = config.get("history", [])

    if not history:
        click.echo("\nNo spending history yet")
        return

    click.echo(f"\nShowing last {limit} transactions:\n")

    for entry in reversed(history[-limit:]):
        timestamp = datetime.fromisoformat(entry["timestamp"])
        click.echo(f"{timestamp.strftime('%Y-%m-%d %H:%M')} | ${entry['cost']:.4f} | {entry.get('job_id', 'N/A')[:8]}")
        if entry.get("description"):
            click.echo(f"  {entry['description'][:80]}")
        click.echo()

    total = sum(e["cost"] for e in history)
    click.echo(f"Total all-time spending: ${total:.2f}")


@budget.command()
def safety():
    """Show cost safety status and limits.

    Displays the defensive cost controls that prevent runaway spending
    from autonomous expert operations.
    """
    from deepr.cli.colors import console, print_key_value
    from deepr.experts.cost_safety import CostSafetyManager, get_cost_safety_manager

    print_header("Cost Safety Status")

    manager = get_cost_safety_manager()
    summary = manager.get_spending_summary()

    # Daily spending
    console.print("[bold]Daily Spending[/bold]")
    daily = summary["daily"]
    percent_color = "green" if daily["percent_used"] < 50 else "yellow" if daily["percent_used"] < 80 else "red"
    print_key_value("Spent", f"${daily['spent']:.2f} / ${daily['limit']:.2f}")
    print_key_value("Remaining", f"${daily['remaining']:.2f}")
    console.print(f"  [dim]Usage:[/dim] [{percent_color}]{daily['percent_used']:.0f}%[/{percent_color}]")
    console.print()

    # Weekly spending
    console.print("[bold]Weekly Spending[/bold]")
    weekly = summary["weekly"]
    percent_color = "green" if weekly["percent_used"] < 50 else "yellow" if weekly["percent_used"] < 80 else "red"
    print_key_value("Spent", f"${weekly['spent']:.2f} / ${weekly['limit']:.2f}")
    print_key_value("Remaining", f"${weekly['remaining']:.2f}")
    console.print(f"  [dim]Usage:[/dim] [{percent_color}]{weekly['percent_used']:.0f}%[/{percent_color}]")
    console.print()

    # Monthly spending
    console.print("[bold]Monthly Spending[/bold]")
    monthly = summary["monthly"]
    percent_color = "green" if monthly["percent_used"] < 50 else "yellow" if monthly["percent_used"] < 80 else "red"
    print_key_value("Spent", f"${monthly['spent']:.2f} / ${monthly['limit']:.2f}")
    print_key_value("Remaining", f"${monthly['remaining']:.2f}")
    console.print(f"  [dim]Usage:[/dim] [{percent_color}]{monthly['percent_used']:.0f}%[/{percent_color}]")
    console.print()

    # Limits
    console.print("[bold]Configured Limits[/bold]")
    limits = summary["limits"]
    print_key_value("Per Operation", f"${limits['per_operation']:.2f}")
    print_key_value("Daily", f"${limits['daily']:.2f}")
    print_key_value("Weekly", f"${limits['weekly']:.2f}")
    print_key_value("Monthly", f"${limits['monthly']:.2f}")
    console.print()

    # Hard limits (cannot be overridden)
    console.print("[bold]Hard Safety Limits[/bold] [dim](cannot be overridden)[/dim]")
    print_key_value("Max Per Operation", f"${CostSafetyManager.ABSOLUTE_MAX_PER_OPERATION:.2f}")
    print_key_value("Max Daily", f"${CostSafetyManager.ABSOLUTE_MAX_DAILY:.2f}")
    print_key_value("Max Weekly", f"${CostSafetyManager.ABSOLUTE_MAX_WEEKLY:.2f}")
    print_key_value("Max Monthly", f"${CostSafetyManager.ABSOLUTE_MAX_MONTHLY:.2f}")
    console.print()

    # Active sessions
    if summary["active_sessions"] > 0:
        console.print(f"[bold]Active Sessions:[/bold] {summary['active_sessions']}")

    console.print("[dim]These limits protect against runaway costs from autonomous agents.[/dim]")
