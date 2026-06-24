"""Budget degradation tiers and the value-of-spend gate.

`CostSafetyManager` enforces hard daily/monthly caps - a cliff: full spend under
the cap, nothing at it. This module adds the graded behavior on top: spend
freely early in the month, get pickier as the monthly pool drains, fall back to
local-only before the cap, and pause (resumably) at it - and spend a metered
dollar only when the expected value of the result justifies it.

It is pure and deterministic: tiers are a function of the monthly drain
fraction, and the value gate is arithmetic over caller-supplied numeric
estimates. It never derives those estimates with a lexical rule and never judges
semantic truth - it gates an irreversible side-effect (metered spend), on the
workflow side of AGENTIC_BALANCE. It governs only metered dollars; local and
plan-quota ($0-at-margin) capacity, which the waterfall reaches first, are never
gated here. Every denial is resumable (defer / use local / wait), never a hard
failure, and nothing raises. Design: docs/design/budget-degradation.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from deepr.experts.cost_safety import CostSafetyManager


class BudgetTier(str, Enum):
    """Spend posture derived from how drained the monthly pool is."""

    NORMAL = "normal"  # spend freely (after the waterfall) for value-clearing work
    CONSERVE = "conserve"  # metered only for high-value/urgent work; hurdle raised
    LOCAL_ONLY = "local_only"  # metered hard-off; local/$0 still runs
    PAUSE_METERED = "pause_metered"  # metered hard-off, resumable pause; never fails


# Tiers whose contract is "no metered spend" regardless of value.
METERED_OFF_TIERS = frozenset({BudgetTier.LOCAL_ONLY, BudgetTier.PAUSE_METERED})


@dataclass(frozen=True)
class SpendPolicyConfig:
    """Tunable thresholds for the tiers and the value gate.

    Defaults are calibrated so a default-value op (0.5 across the four factors)
    at the reference cost clears NORMAL but defers in CONSERVE.
    """

    conserve_drain: float = 0.70
    local_only_drain: float = 0.90
    pause_drain: float = 1.00
    reference_cost: float = 0.50  # a "typical" metered op; est_cost is scaled by this
    normal_multiple: float = 0.05  # value hurdle multiplier in NORMAL (low bar)
    conserve_multiple: float = 0.20  # higher bar in CONSERVE (rises as the pool drains)


@dataclass(frozen=True)
class SpendDecision:
    """The verdict on one prospective metered op."""

    allowed: bool
    tier: BudgetTier
    reason: str
    benefit: float
    hurdle: float
    pausable: bool  # a denial here is resumable (defer/wait), never a hard failure

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "tier": self.tier.value,
            "reason": self.reason,
            "benefit": round(self.benefit, 4),
            "hurdle": round(self.hurdle, 4),
            "pausable": self.pausable,
        }


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def budget_tier(spent: float, cap: float, config: SpendPolicyConfig | None = None) -> BudgetTier:
    """Tier from the monthly drain fraction (``spent / cap``).

    A non-positive cap means "no monthly governance configured" -> NORMAL (the
    absolute caps in CostSafetyManager still protect). Negative spend is treated
    as zero.
    """
    cfg = config or SpendPolicyConfig()
    if cap <= 0:
        return BudgetTier.NORMAL
    drain = max(0.0, spent) / cap
    if drain >= cfg.pause_drain:
        return BudgetTier.PAUSE_METERED
    if drain >= cfg.local_only_drain:
        return BudgetTier.LOCAL_ONLY
    if drain >= cfg.conserve_drain:
        return BudgetTier.CONSERVE
    return BudgetTier.NORMAL


def evaluate_spend(
    *,
    spent: float,
    cap: float,
    est_cost: float,
    gap_closure: float = 0.5,
    value: float = 0.5,
    urgency: float = 0.5,
    volatility: float = 0.5,
    config: SpendPolicyConfig | None = None,
) -> SpendDecision:
    """Decide whether a prospective metered op should run, given the pool state.

    Call this only for metered spend the waterfall has already chosen (local and
    plan-quota are free and never gated here). The four benefit factors are
    caller-supplied estimates in ``[0, 1]``; defaults assume "unknown" and clamp
    out-of-range values. Returns a resumable decision; never raises.
    """
    cfg = config or SpendPolicyConfig()
    tier = budget_tier(spent, cap, cfg)

    if tier == BudgetTier.PAUSE_METERED:
        return SpendDecision(
            False, tier, "monthly budget exhausted; metered paused (resumable), local stays $0", 0.0, 0.0, True
        )
    if tier == BudgetTier.LOCAL_ONLY:
        return SpendDecision(False, tier, "monthly budget >=90% used; metered off, local stays $0", 0.0, 0.0, True)

    benefit = _clamp01(gap_closure) * _clamp01(value) * _clamp01(urgency) * _clamp01(volatility)
    multiple = cfg.normal_multiple if tier == BudgetTier.NORMAL else cfg.conserve_multiple
    cost_ratio = est_cost / cfg.reference_cost if cfg.reference_cost > 0 else est_cost
    hurdle = multiple * max(0.0, cost_ratio)
    allowed = benefit >= hurdle
    if allowed:
        reason = f"value {benefit:.3f} clears {tier.value} hurdle {hurdle:.3f}"
    else:
        reason = f"value {benefit:.3f} below {tier.value} hurdle {hurdle:.3f}; defer or use local"
    return SpendDecision(allowed, tier, reason, benefit, hurdle, pausable=not allowed)


def tier_from_manager(manager: CostSafetyManager, config: SpendPolicyConfig | None = None) -> BudgetTier:
    """Current tier from a CostSafetyManager's live monthly spend vs cap."""
    return budget_tier(manager.monthly_cost, manager.max_monthly, config)


def describe_tier(manager: CostSafetyManager, config: SpendPolicyConfig | None = None) -> dict[str, Any]:
    """Read-only ``$0`` snapshot of the current spend posture for operators/UX."""
    tier = tier_from_manager(manager, config)
    drain = manager.monthly_cost / manager.max_monthly if manager.max_monthly > 0 else 0.0
    return {
        "tier": tier.value,
        "monthly_spent": round(manager.monthly_cost, 4),
        "monthly_cap": round(manager.max_monthly, 4),
        "drain_percent": round(drain * 100.0, 1),
        "metered_off": tier in METERED_OFF_TIERS,
    }
