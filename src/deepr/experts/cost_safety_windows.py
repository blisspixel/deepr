"""Pure projection checks for metered spend windows."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from math import isfinite

from deepr.observability.cost_ledger import CostLedgerEvent


@dataclass
class NarrowingSpendLimit:
    """Track mutable caller narrowing separately from operator authority."""

    authority: float
    caller_override: float | None = None
    effective: float = field(init=False)

    def __post_init__(self) -> None:
        self.effective = self.authority

    def refresh(self, current: float, authority: float) -> float:
        """Observe a public-field override, then apply new authority safely."""
        if not isfinite(current) or current < 0:
            raise ValueError("Spend limits must be finite and non-negative")
        if current != self.effective:
            self.caller_override = current if self.caller_override is None else min(self.caller_override, current)
        self.authority = authority
        self.effective = min(authority, self.caller_override) if self.caller_override is not None else authority
        return self.effective


@dataclass(frozen=True)
class PolicySpendWindows:
    """Calendar settlement plus cumulative wallet drawdown for one snapshot."""

    daily: float
    weekly: float
    monthly: float
    wallet_consumed: float | None


def settled_spend_windows(
    events: list[CostLedgerEvent],
    *,
    now: datetime,
) -> tuple[float, float, float]:
    """Calendar-window spend in daily, weekly, and monthly order."""
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = day_start - timedelta(days=day_start.weekday())
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return (
        float(sum(event.cost_usd for event in events if event.timestamp >= day_start)),
        float(sum(event.cost_usd for event in events if event.timestamp >= week_start)),
        float(sum(event.cost_usd for event in events if event.timestamp >= month_start)),
    )


def policy_spend_windows(
    events: list[CostLedgerEvent],
    *,
    now: datetime,
    wallet_baseline_usd: float | None,
    calendar_periods: frozenset[str],
) -> PolicySpendWindows:
    """Shape calendar windows and optional cumulative wallet drawdown."""
    daily, weekly, monthly = settled_spend_windows(events, now=now)
    if wallet_baseline_usd is None:
        return PolicySpendWindows(daily, weekly, monthly, None)
    total_settled = float(sum(event.cost_usd for event in events))
    if total_settled < wallet_baseline_usd:
        raise ValueError("canonical settled cost is below the spend wallet baseline")
    consumed = total_settled - wallet_baseline_usd
    return PolicySpendWindows(
        daily if "daily" in calendar_periods else consumed,
        weekly if "weekly" in calendar_periods else consumed,
        monthly if "monthly" in calendar_periods else consumed,
        consumed,
    )


def projected_window_limit_reason(
    estimated_cost: float,
    windows: Iterable[tuple[str, float, float, float]],
) -> str:
    """Return the first window denial, ordered from narrowest to widest."""
    for label, spent, reserved, limit in windows:
        if spent + reserved + estimated_cost > limit:
            return (
                f"{label} limit ${limit:.2f} would be exceeded "
                f"(spent ${spent:.2f}, reserved ${reserved:.2f}, +${estimated_cost:.2f})"
            )
    return ""
