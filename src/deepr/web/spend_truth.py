"""Spend-truth helpers for the dashboard: budget breach and artifact audit.

A 30-job campaign once billed $37.79 while the dashboard showed nothing and
zero report artifacts survived. These helpers give the web API the same
reconciled numbers the CLI approval gate and `deepr costs doctor` use, so
over-budget state and orphaned spend are first-class facts the UI renders
loudly instead of surprises found on a bill.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path


def budget_gate_fields(monthly_spending: float, controller_monthly_limit: float) -> dict:
    """Reconcile the env-cap controller limit with the approval-gate budget.

    The CLI gate spends against budget.json's monthly limit, which can differ
    from DEEPR_MAX_COST_PER_MONTH. Whichever positive ceiling is LOWER governs,
    and a breach is reported explicitly.
    """
    try:
        from deepr.cli.commands.budget import load_budget_config

        budget_monthly_limit = float(load_budget_config().get("monthly_limit", 0) or 0)
    except Exception:
        budget_monthly_limit = 0.0
    positive = [x for x in (controller_monthly_limit, budget_monthly_limit) if x and x > 0]
    effective = min(positive) if positive else 0.0
    return {
        "budget_monthly_limit": budget_monthly_limit,
        "effective_monthly_limit": effective,
        "over_budget": bool(effective and monthly_spending > effective),
    }


def audit_spend_integrity(days: int, reports_root: Path) -> dict:
    """Classify paid ledger events in the window as artifact-matched or orphaned.

    Same classifier as `deepr costs doctor`: settled spend either maps to a
    report directory on disk (by job-id fragment) or is money with nothing to
    show for it.
    """
    from deepr.cli.commands.costs import _doctor_classify
    from deepr.observability.cost_ledger import CostLedger

    cutoff = datetime.now(UTC) - timedelta(days=days)
    dir_names = [d.name for d in reports_root.iterdir() if d.is_dir()] if reports_root.exists() else []
    matched, orphaned = _doctor_classify(CostLedger().get_events(), dir_names, cutoff)
    return {
        "days": days,
        "matched_spend": round(sum(e["cost_usd"] for e in matched), 2),
        "orphaned_spend": round(sum(e["cost_usd"] for e in orphaned), 2),
        "matched_events": len(matched),
        "orphaned_events": len(orphaned),
    }
