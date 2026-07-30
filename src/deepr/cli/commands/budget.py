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
    _with_verified_authorization,
    apply_paid_api_freeze,
    budget_file_path,
    parse_operator_budget,
    read_operator_budget,
    resolve_spend_caps,
    spend_policy_lock,
)


def get_budget_file() -> Path:
    """Get budget configuration file path."""
    return budget_file_path()


def _next_month_start(now: datetime | None = None) -> datetime:
    """Return the first UTC instant of the next calendar month."""
    current = now or datetime.now(UTC)
    current_month = current.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if current_month.month == 12:
        return current_month.replace(year=current_month.year + 1, month=1)
    return current_month.replace(month=current_month.month + 1)


def _load_budget_config_unlocked() -> dict[str, Any]:
    budget_file = get_budget_file()
    if not budget_file.exists():
        return {
            "monthly_limit": 0,
            "paid_api_frozen": True,
            "freeze_reason": "paid API account controls are not configured",
            "freeze_kind": "unconfigured",
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
        return CostLedger().with_locked_accounting_events(
            lambda events: sum(event.cost_usd for event in events if event.timestamp >= month_start)
        )
    except Exception:
        return None


def _durable_active_cost() -> float | None:
    """Return strictly reconciled active paid holds, or None on uncertainty."""
    try:
        from deepr.experts.research_reservation_store import ResearchReservationStore

        return ResearchReservationStore().active_cost()
    except Exception:
        return None


def _atomic_monthly_exposure():
    """Return settled, active, and unresolved exposure from one locked view."""
    try:
        from deepr.experts.research_reservation_store import ResearchReservationStore

        return ResearchReservationStore().exposure_snapshot()
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
        monthly_limit = resolve_spend_caps()["monthly"]
    except Exception:
        return False

    exposure = _atomic_monthly_exposure()
    if monthly_limit <= 0 or exposure is None:
        return False

    # Spend = max(side counter, canonical ledger) so
    # spend recorded by other entry points (web, MCP, expert learning)
    # counts against the month even if record_spending never saw it.
    current_spending = max(config.get("monthly_spending", 0.0), exposure.monthly_settled_cost) + exposure.active_cost
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
        deepr budget set 5       # Repository-wide $5/month ceiling
        deepr budget set 0       # Freeze paid API dispatch
    """
    print_header("Budget Configuration")

    def update(config: dict[str, Any]) -> None:
        config["monthly_limit"] = amount
        authorization = config.get("paid_api_authorization")
        has_recovered_authorization = isinstance(authorization, dict) and bool(
            authorization.get("recovered_freeze_id") and authorization.get("recovered_frozen_at")
        )
        if not config.get("freeze_id") and (
            amount == 0 or config.get("paid_api_frozen", False) or not has_recovered_authorization
        ):
            apply_paid_api_freeze(
                config,
                reason=(
                    "paid API monthly ceiling is zero"
                    if amount == 0
                    else str(config.get("freeze_reason") or "paid API account controls are not configured")
                ),
                kind="zero_ceiling" if amount == 0 else "unconfigured",
            )

    config = mutate_budget_config(update)

    if amount == 0:
        click.echo("\nBudget: Paid API dispatch frozen ($0 hard ceiling)")
    else:
        # Show the same reconciled number the approval gate uses. The session
        # counter alone once displayed $0.00 while the canonical ledger held
        # $37.99 of campaign spend - the display must never lie about money.
        ledger_spend = _ledger_month_spend()
        active_cost = _durable_active_cost()
        settled = max(float(config.get("monthly_spending", 0) or 0), ledger_spend or 0.0)
        effective_limit = resolve_spend_caps()["monthly"]
        click.echo(f"\nConfigured budget: ${amount:.2f}/month")
        click.echo(f"Effective hard ceiling: ${effective_limit:.2f}/month")
        if ledger_spend is None or active_cost is None:
            click.echo("Current exposure: UNKNOWN")
            click.echo("Warning: canonical money state is unreadable; paid dispatch remains blocked.")
        else:
            click.echo(f"Settled spending: ${settled:.2f}")
            click.echo(f"Active durable holds: ${active_cost:.2f}")
            click.echo(f"Current exposure: ${settled + active_cost:.2f}")
        click.echo(f"Resets: {_next_month_start().strftime('%B %d, %Y')} UTC")


@budget.command()
def status():
    """Show current budget status."""
    print_header("Budget Status")

    config = load_budget_config()
    configured_monthly = float(config.get("monthly_limit", 0) or 0)
    effective_monthly = resolve_spend_caps()["monthly"]
    # The approval gate spends against max(session counter, canonical ledger),
    # so the status display must show that same reconciled number. Showing only
    # the session counter once reported $0.00 while the ledger held $37.99 of
    # campaign spend recorded by other entry points - the exact blindfold that
    # let a surprise bill go unnoticed for 24 days.
    counter_spending = float(config.get("monthly_spending", 0.0) or 0.0)
    exposure = _atomic_monthly_exposure()
    ledger_unreadable = exposure is None
    ledger_spending = exposure.monthly_settled_cost if exposure is not None else 0.0
    settled_spending = max(counter_spending, ledger_spending)
    holds_unreadable = exposure is None
    active_cost = exposure.active_cost if exposure is not None else 0.0
    money_state_unreadable = ledger_unreadable or holds_unreadable
    current_exposure = settled_spending + active_cost
    current_month = config.get("current_month", datetime.now(UTC).strftime("%Y-%m"))

    click.echo(f"\nSettled this month: ${settled_spending:.2f}")
    click.echo(f"Active durable holds: {'UNKNOWN' if holds_unreadable else f'${active_cost:.2f}'}")

    operator = read_operator_budget()
    if operator.frozen:
        reason = operator.freeze_reason or "paid API safety freeze"
        click.echo(f"Mode: Paid API frozen ({reason})")
        click.echo(f"Configured monthly ceiling: ${configured_monthly:.2f}")
        click.echo("Effective monthly ceiling: $0.00")
    elif effective_monthly == 0:
        click.echo("Mode: Paid API frozen ($0 hard ceiling)")
    elif money_state_unreadable:
        click.echo("Mode: Paid API blocked (canonical money state is unreadable)")
        click.echo(f"Budget: UNKNOWN / ${effective_monthly:.2f}")
        click.echo("Remaining: $0.00 (fail closed)")
    else:
        percentage = current_exposure / effective_monthly * 100
        remaining = max(0.0, effective_monthly - current_exposure)
        overage = max(0.0, current_exposure - effective_monthly)

        click.echo(f"Budget: ${current_exposure:.2f} / ${effective_monthly:.2f} ({percentage:.0f}%)")
        if configured_monthly != effective_monthly:
            click.echo(f"Configured monthly budget: ${configured_monthly:.2f}; tighter policy is active")
        click.echo(f"Remaining: ${remaining:.2f}")
        if overage > 0:
            click.echo(f"Over hard ceiling by: ${overage:.2f}")
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

    click.echo(f"Resets: {_next_month_start().strftime('%B %d, %Y')} UTC")


@budget.command()
@click.option("--reason", default="manual operator freeze", show_default=True)
def freeze(reason: str) -> None:
    """Immediately block every paid API reservation."""
    print_header("Budget Freeze")

    def update(config: dict[str, Any]) -> None:
        apply_paid_api_freeze(
            config,
            reason=reason.strip() or "manual operator freeze",
            kind="manual",
        )

    mutate_budget_config(update)
    click.echo("\nPaid API dispatch is frozen. Local and safety-eligible plan capacity remain available.")


@budget.command()
@click.option(
    "--evidence-id",
    "evidence_ids",
    multiple=True,
    required=True,
    help="Content-addressed account-control evidence ID; repeat for each provider",
)
def unfreeze(evidence_ids: tuple[str, ...]) -> None:
    """Remove a freeze only with current verified account-control evidence."""
    print_header("Budget Unfreeze")
    result: dict[str, float] = {}

    def update(config: dict[str, Any]) -> None:
        try:
            current = parse_operator_budget(config)
            if config.get("paid_api_frozen") is not True or not current.freeze_id or current.frozen_at is None:
                raise click.ClickException(
                    "A current typed freeze ID and timestamp are required; paid dispatch remains frozen."
                )
            exposure = _atomic_monthly_exposure()
            if exposure is None:
                raise click.ClickException("Canonical money state is unreadable; paid dispatch remains frozen.")
            if exposure.unresolved_count:
                raise click.ClickException(
                    "Provider work has unresolved durable holds; paid dispatch remains frozen until settlement is reconciled."
                )
            if exposure.active_cost > 0:
                raise click.ClickException(
                    "Active durable paid holds must be settled or refunded before unfreezing paid dispatch."
                )
            from deepr.observability.cost_ledger import current_cost_state_id
            from deepr.observability.provider_account_controls import (
                ProviderAccountControlError,
                verify_paid_api_authorization,
            )

            try:
                authorization = verify_paid_api_authorization(
                    evidence_ids,
                    expected_freeze_id=current.freeze_id,
                    expected_frozen_at=current.frozen_at,
                    monthly_limit_usd=current.monthly_limit,
                )
            except ProviderAccountControlError as exc:
                raise click.ClickException(
                    f"Verified provider account-control evidence is required; paid dispatch remains frozen: {exc}"
                ) from exc
            candidate = _with_verified_authorization(
                OperatorBudget(
                    configured=True,
                    monthly_limit=current.monthly_limit,
                    frozen=True,
                    authorization_recovered_frozen_at=current.frozen_at,
                ),
                authorization,
            )
            effective_limit = resolve_spend_caps(
                operator_budget=candidate,
                provider=authorization.providers[0],
            )["monthly"]
        except (TypeError, ValueError) as exc:
            raise click.ClickException(str(exc)) from exc
        current_spending = (
            max(float(config.get("monthly_spending", 0.0) or 0.0), exposure.monthly_settled_cost) + exposure.active_cost
        )
        if effective_limit <= 0:
            raise click.ClickException("Set a positive finite monthly budget before unfreezing paid dispatch.")
        if current_spending >= effective_limit:
            raise click.ClickException(
                f"Current monthly spend ${current_spending:.2f} has exhausted the ${effective_limit:.2f} hard ceiling. "
                "Wait for the UTC month rollover or explicitly raise the ceiling before unfreezing."
            )
        config["paid_api_authorization"] = {
            "authority": "verified_by_deepr",
            "evidence_ids": list(authorization.evidence_ids),
            "valid_until": authorization.valid_until.isoformat(),
            "recovered_freeze_id": current.freeze_id,
            "recovered_frozen_at": current.frozen_at.isoformat(),
            "cost_state_id": current_cost_state_id(),
        }
        config["paid_api_frozen"] = False
        config["freeze_reason"] = ""
        config.pop("frozen_at", None)
        config.pop("freeze_id", None)
        config.pop("freeze_kind", None)
        result["headroom"] = effective_limit - current_spending

    mutate_budget_config(update)
    click.echo(f"\nPaid API dispatch unfrozen with ${result['headroom']:.2f} monthly headroom.")


@budget.command()
@click.option(
    "--limit",
    "-n",
    default=10,
    type=click.IntRange(min=1, max=1000),
    show_default=True,
    help="Number of recent canonical transactions to show",
)
def history(limit: int):
    """Show canonical append-only spending history."""
    print_header("Spending History")

    try:
        from deepr.observability.cost_ledger import CostLedger

        history, total = CostLedger().with_locked_accounting_events(
            lambda events: ([event for event in events if event.cost_usd > 0], sum(event.cost_usd for event in events))
        )
    except Exception as exc:
        raise click.ClickException("Canonical cost ledger is unreadable; spending history is unavailable.") from exc

    if not history:
        click.echo("\nNo canonical spending history yet")
        return

    click.echo(f"\nShowing last {min(limit, len(history))} canonical transactions:\n")

    for entry in reversed(history[-limit:]):
        target = entry.task_id or entry.session_id or "N/A"
        model = entry.model or "unknown-model"
        click.echo(f"{entry.timestamp.strftime('%Y-%m-%d %H:%M')} | ${entry.cost_usd:.6f} | {entry.provider}/{model}")
        click.echo(f"  {entry.operation} | {entry.source} | {target[:80]}")
        click.echo()

    click.echo(f"Total all-time settled spending: ${total:.6f}")
    active_cost = _durable_active_cost()
    click.echo(f"Active durable holds: {'UNKNOWN' if active_cost is None else f'${active_cost:.6f}'}")


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
    active_cost = _durable_active_cost()

    # Daily spending
    console.print("[bold]Daily Spending[/bold]")
    daily = summary["daily"]
    percent_color = "green" if daily["percent_used"] < 50 else "yellow" if daily["percent_used"] < 80 else "red"
    print_key_value("Settled", f"${daily['spent']:.2f} / ${daily['limit']:.2f}")
    print_key_value("Window Remaining", f"${daily['remaining']:.2f}")
    console.print(f"  [dim]Usage:[/dim] [{percent_color}]{daily['percent_used']:.0f}%[/{percent_color}]")
    console.print()

    # Weekly spending
    console.print("[bold]Weekly Spending[/bold]")
    weekly = summary["weekly"]
    percent_color = "green" if weekly["percent_used"] < 50 else "yellow" if weekly["percent_used"] < 80 else "red"
    print_key_value("Settled", f"${weekly['spent']:.2f} / ${weekly['limit']:.2f}")
    print_key_value("Window Remaining", f"${weekly['remaining']:.2f}")
    console.print(f"  [dim]Usage:[/dim] [{percent_color}]{weekly['percent_used']:.0f}%[/{percent_color}]")
    console.print()

    # Monthly spending
    console.print("[bold]Monthly Spending[/bold]")
    monthly = summary["monthly"]
    percent_color = "green" if monthly["percent_used"] < 50 else "yellow" if monthly["percent_used"] < 80 else "red"
    print_key_value("Settled", f"${monthly['spent']:.2f} / ${monthly['limit']:.2f}")
    print_key_value("Window Remaining", f"${monthly['remaining']:.2f}")
    console.print(f"  [dim]Usage:[/dim] [{percent_color}]{monthly['percent_used']:.0f}%[/{percent_color}]")
    console.print()

    console.print("[bold]Durable Reservation Exposure[/bold]")
    if active_cost is None:
        print_key_value("Active Holds", "UNKNOWN")
        print_key_value("Maximum New Paid Call", "$0.00 (fail closed)")
    else:
        exposure = monthly["spent"] + active_cost
        authorizable_headroom = max(
            0.0,
            min(
                summary["limits"]["per_operation"],
                daily["limit"] - daily["spent"] - active_cost,
                weekly["limit"] - weekly["spent"] - active_cost,
                monthly["limit"] - monthly["spent"] - active_cost,
            ),
        )
        print_key_value("Active Holds", f"${active_cost:.2f}")
        print_key_value("Settled + Holds", f"${exposure:.2f} / ${monthly['limit']:.2f}")
        print_key_value("Maximum New Paid Call", f"${authorizable_headroom:.2f}")
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
