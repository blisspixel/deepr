"""Budget management commands."""

import json
from datetime import datetime
from pathlib import Path

import click

from deepr.cli.colors import print_header


def get_budget_file():
    """Get budget configuration file path."""
    config_dir = Path.home() / ".deepr"
    config_dir.mkdir(exist_ok=True)
    return config_dir / "budget.json"


def load_budget_config():
    """Load budget configuration."""
    budget_file = get_budget_file()
    if not budget_file.exists():
        return {
            "monthly_limit": 0,  # 0 = confirm every job
            "current_month": datetime.now().strftime("%Y-%m"),
            "monthly_spending": 0.0,
            "history": [],
        }

    with open(budget_file, encoding="utf-8") as f:
        config = json.load(f)

    # Reset if new month
    current_month = datetime.now().strftime("%Y-%m")
    if config.get("current_month") != current_month:
        config["current_month"] = current_month
        config["monthly_spending"] = 0.0

    return config


def save_budget_config(config):
    """Save budget configuration."""
    budget_file = get_budget_file()
    with open(budget_file, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


# Cumulative auto-approve ceiling for cautious mode (monthly_limit=0): the
# under-$1 convenience stops without confirmation once the month's real
# (ledger) spend reaches this. Set an explicit budget to go higher.
CAUTIOUS_MODE_MONTHLY_CEILING = 25.0


def _ledger_month_spend() -> float:
    """Current calendar-month spend from the canonical cost ledger.

    The budget.json counter only sees spend recorded through
    record_spending; the ledger sees every recorder (CLI, web, MCP,
    expert learning). Budget decisions use whichever is HIGHER, so a
    path that bypassed the side counter cannot make the month look
    cheaper than it was. Best-effort: a ledger read failure returns 0
    and the side counter still applies.
    """
    try:
        from datetime import UTC

        from deepr.observability.cost_ledger import CostLedger

        now = datetime.now(UTC)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return CostLedger().get_total_cost(start_date=month_start)
    except Exception:
        return 0.0


def check_budget_approval(estimated_cost: float) -> bool:
    """
    Check if job should auto-execute based on budget.

    Returns:
        True if approved, False if needs manual confirmation
    """
    config = load_budget_config()
    monthly_limit = config.get("monthly_limit", 0)

    # Mode 1: Confirm every job (budget = 0)
    if monthly_limit == 0:
        # QoL: Auto-approve small jobs under $1 even in cautious mode -
        # but only up to a cumulative monthly ceiling (canonical ledger).
        # Without the ceiling, a headless loop of $0.99 jobs was unbounded:
        # "under $1 each" must never become a surprise bill in aggregate.
        if estimated_cost < 1.0 and _ledger_month_spend() + estimated_cost < CAUTIOUS_MODE_MONTHLY_CEILING:
            return True
        return False

    # Mode 2: Unlimited (budget = -1)
    if monthly_limit == -1:
        return True

    # Mode 3: Budget limit. Spend = max(side counter, canonical ledger) so
    # spend recorded by other entry points (web, MCP, expert learning)
    # counts against the month even if record_spending never saw it.
    current_spending = max(config.get("monthly_spending", 0.0), _ledger_month_spend())
    new_total = current_spending + estimated_cost

    # Auto-approve if under 80% of budget
    if new_total < monthly_limit * 0.8:
        return True

    # Require confirmation if approaching or exceeding budget
    return False


def record_spending(cost: float, job_id: str, description: str):
    """Record spending in budget."""
    config = load_budget_config()
    config["monthly_spending"] = config.get("monthly_spending", 0.0) + cost

    # Add to history
    if "history" not in config:
        config["history"] = []

    config["history"].append(
        {"timestamp": datetime.now().isoformat(), "cost": cost, "job_id": job_id, "description": description}
    )

    # Keep last 100 entries
    config["history"] = config["history"][-100:]

    save_budget_config(config)


@click.group()
def budget():
    """Manage monthly research budget."""
    pass


@budget.command()
@click.argument("amount", type=float)
def set(amount: float):
    """
    Set monthly research budget.

    Examples:
        deepr budget set 50      # $50/month budget
        deepr budget set 0       # Confirm every job
        deepr budget set -1      # Unlimited (never confirm)
    """
    print_header("Budget Configuration")

    config = load_budget_config()
    config["monthly_limit"] = amount
    save_budget_config(config)

    if amount == 0:
        click.echo("\nBudget: Confirm every job (cautious mode)")
    elif amount == -1:
        click.echo("\nBudget: Unlimited (trust mode)")
    else:
        click.echo(f"\nBudget: ${amount:.2f}/month")
        click.echo(f"Current spending: ${config.get('monthly_spending', 0):.2f}")
        click.echo(f"Resets: {datetime.now().strftime('%B')} 1")


@budget.command()
def status():
    """Show current budget status."""
    print_header("Budget Status")

    config = load_budget_config()
    monthly_limit = config.get("monthly_limit", 0)
    current_spending = config.get("monthly_spending", 0.0)
    current_month = config.get("current_month", datetime.now().strftime("%Y-%m"))

    if monthly_limit == 0:
        click.echo("\nMode: Confirm every job (cautious mode)")
    elif monthly_limit == -1:
        click.echo("\nMode: Unlimited (trust mode)")
    else:
        percentage = (current_spending / monthly_limit * 100) if monthly_limit > 0 else 0
        remaining = monthly_limit - current_spending

        click.echo(f"\nBudget: ${current_spending:.2f} / ${monthly_limit:.2f} ({percentage:.0f}%)")
        click.echo(f"Remaining: ${remaining:.2f}")

        if percentage >= 90:
            click.echo("\nWarning: Budget nearly exhausted")
        elif percentage >= 80:
            click.echo("\nNote: Approaching budget limit")

    click.echo(f"\nCurrent month: {current_month}")

    # Next reset
    next_month = datetime.now().replace(day=1)
    if next_month.month == 12:
        next_month = next_month.replace(year=next_month.year + 1, month=1)
    else:
        next_month = next_month.replace(month=next_month.month + 1)
    click.echo(f"Resets: {next_month.strftime('%B %d, %Y')}")


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
    print_key_value("Monthly", f"${limits['monthly']:.2f}")
    console.print()

    # Hard limits (cannot be overridden)
    console.print("[bold]Hard Safety Limits[/bold] [dim](cannot be overridden)[/dim]")
    print_key_value("Max Per Operation", f"${CostSafetyManager.ABSOLUTE_MAX_PER_OPERATION:.2f}")
    print_key_value("Max Daily", f"${CostSafetyManager.ABSOLUTE_MAX_DAILY:.2f}")
    print_key_value("Max Monthly", f"${CostSafetyManager.ABSOLUTE_MAX_MONTHLY:.2f}")
    console.print()

    # Active sessions
    if summary["active_sessions"] > 0:
        console.print(f"[bold]Active Sessions:[/bold] {summary['active_sessions']}")

    console.print("[dim]These limits protect against runaway costs from autonomous agents.[/dim]")
