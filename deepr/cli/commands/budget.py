"""Budget management commands."""

import click
import json
from pathlib import Path
from datetime import datetime
from deepr.branding import print_section_header


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
            "history": []
        }

    with open(budget_file, 'r') as f:
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
    with open(budget_file, 'w') as f:
        json.dump(config, f, indent=2)


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
        return False

    # Mode 2: Unlimited (budget = -1)
    if monthly_limit == -1:
        return True

    # Mode 3: Budget limit
    current_spending = config.get("monthly_spending", 0.0)
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

    config["history"].append({
        "timestamp": datetime.now().isoformat(),
        "cost": cost,
        "job_id": job_id,
        "description": description
    })

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
    print_section_header("Budget Configuration")

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
    print_section_header("Budget Status")

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
    print_section_header("Spending History")

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
