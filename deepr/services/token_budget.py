"""Token budget allocation for multi-phase research.

Manages token budgets across research phases, with support for:
- Phase-weighted allocation
- Dynamic reallocation of unused tokens
- Synthesis phase reservation

Usage:
    from deepr.services.token_budget import TokenBudgetAllocator

    allocator = TokenBudgetAllocator(total_budget=50000)

    # Create a budget plan
    plan = allocator.create_plan(
        num_phases=5,
        phase_weights={1: 0.15, 2: 0.2, 3: 0.2, 4: 0.2, 5: 0.25}
    )

    # Record usage and reallocate
    plan = allocator.record_usage(plan, phase=1, tokens_used=5000)
    plan = allocator.reallocate_unused(plan, from_phase=1)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from deepr.core.constants import (
    MAX_CONTEXT_TOKENS,
    TOKEN_BUDGET_DEFAULT,
    TOKEN_BUDGET_SYNTHESIS_RESERVE_PCT,
)


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


class AllocationStrategy(Enum):
    """Budget allocation strategies."""

    EQUAL = "equal"  # Equal allocation per phase
    WEIGHTED = "weighted"  # Custom weights per phase
    FRONT_LOADED = "front_loaded"  # More for early phases
    BACK_LOADED = "back_loaded"  # More for later phases
    ADAPTIVE = "adaptive"  # Adjusts based on actual usage


@dataclass
class PhaseAllocation:
    """Budget allocation for a single phase."""

    phase: int
    allocated: int
    used: int = 0
    remaining: int = 0
    status: str = "pending"  # pending, active, completed

    def __post_init__(self):
        if self.remaining == 0:
            self.remaining = self.allocated

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "allocated": self.allocated,
            "used": self.used,
            "remaining": self.remaining,
            "utilization": self.used / max(self.allocated, 1),
            "status": self.status,
        }


@dataclass
class BudgetPlan:
    """Complete budget plan for a research session."""

    total_budget: int
    synthesis_reserve: int
    phases: dict[int, PhaseAllocation]
    strategy: AllocationStrategy
    created_at: datetime = field(default_factory=_utc_now)
    reallocation_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_budget": self.total_budget,
            "synthesis_reserve": self.synthesis_reserve,
            "working_budget": self.total_budget - self.synthesis_reserve,
            "phases": {k: v.to_dict() for k, v in self.phases.items()},
            "strategy": self.strategy.value,
            "created_at": self.created_at.isoformat(),
            "reallocation_count": self.reallocation_count,
            "total_used": sum(p.used for p in self.phases.values()),
            "total_remaining": sum(p.remaining for p in self.phases.values()),
        }

    @property
    def total_used(self) -> int:
        """Get total tokens used across all phases."""
        return sum(p.used for p in self.phases.values())

    @property
    def total_remaining(self) -> int:
        """Get total remaining tokens."""
        return sum(p.remaining for p in self.phases.values())

    @property
    def overall_utilization(self) -> float:
        """Get overall budget utilization."""
        working = self.total_budget - self.synthesis_reserve
        return self.total_used / max(working, 1)


class TokenBudgetAllocator:
    """Manages token budgets across research phases.

    Supports multiple allocation strategies and dynamic reallocation
    of unused tokens to maximize research depth.

    Attributes:
        total_budget: Total token budget
        synthesis_reserve_pct: Percentage reserved for synthesis
        max_context_per_phase: Maximum context tokens per phase
    """

    def __init__(
        self,
        total_budget: Optional[int] = None,
        synthesis_reserve_pct: Optional[float] = None,
        max_context_per_phase: Optional[int] = None,
    ):
        """Initialize the allocator.

        Args:
            total_budget: Total token budget (default from constants)
            synthesis_reserve_pct: Synthesis reserve percentage (default from constants)
            max_context_per_phase: Max context per phase (default from constants)
        """
        self.total_budget = total_budget or TOKEN_BUDGET_DEFAULT
        self.synthesis_reserve_pct = synthesis_reserve_pct or TOKEN_BUDGET_SYNTHESIS_RESERVE_PCT
        self.max_context_per_phase = max_context_per_phase or MAX_CONTEXT_TOKENS

    def create_plan(
        self,
        num_phases: int,
        phase_weights: Optional[dict[int, float]] = None,
        strategy: AllocationStrategy = AllocationStrategy.WEIGHTED,
    ) -> BudgetPlan:
        """Create a budget plan for phases.

        Args:
            num_phases: Number of research phases
            phase_weights: Optional custom weights (must sum to 1.0)
            strategy: Allocation strategy to use

        Returns:
            BudgetPlan with allocations
        """
        # Calculate synthesis reserve
        synthesis_reserve = int(self.total_budget * self.synthesis_reserve_pct)
        working_budget = self.total_budget - synthesis_reserve

        # Get weights based on strategy
        if phase_weights:
            weights = phase_weights
        else:
            weights = self._get_weights_for_strategy(num_phases, strategy)

        # Normalize weights
        total_weight = sum(weights.values())
        weights = {k: v / total_weight for k, v in weights.items()}

        # Create phase allocations
        phases = {}
        for phase in range(1, num_phases + 1):
            weight = weights.get(phase, 1.0 / num_phases)
            allocated = min(
                int(working_budget * weight),
                self.max_context_per_phase,
            )
            phases[phase] = PhaseAllocation(
                phase=phase,
                allocated=allocated,
            )

        return BudgetPlan(
            total_budget=self.total_budget,
            synthesis_reserve=synthesis_reserve,
            phases=phases,
            strategy=strategy,
        )

    def record_usage(
        self,
        plan: BudgetPlan,
        phase: int,
        tokens_used: int,
    ) -> BudgetPlan:
        """Record token usage for a phase.

        Args:
            plan: Current budget plan
            phase: Phase number
            tokens_used: Tokens used in this phase

        Returns:
            Updated BudgetPlan
        """
        if phase not in plan.phases:
            return plan

        allocation = plan.phases[phase]
        allocation.used = tokens_used
        allocation.remaining = max(0, allocation.allocated - tokens_used)
        allocation.status = "completed"

        return plan

    def reallocate_unused(
        self,
        plan: BudgetPlan,
        from_phase: int,
    ) -> BudgetPlan:
        """Reallocate unused tokens from a phase.

        Distributes unused tokens to remaining phases proportionally.

        Args:
            plan: Current budget plan
            from_phase: Phase to reallocate from

        Returns:
            Updated BudgetPlan with reallocation
        """
        if from_phase not in plan.phases:
            return plan

        source = plan.phases[from_phase]
        unused = source.remaining

        if unused <= 0:
            return plan

        # Find pending phases
        pending_phases = [p for p, alloc in plan.phases.items() if p > from_phase and alloc.status == "pending"]

        if not pending_phases:
            return plan

        # Distribute proportionally
        per_phase = unused // len(pending_phases)
        remainder = unused % len(pending_phases)

        for i, phase in enumerate(pending_phases):
            bonus = per_phase + (1 if i < remainder else 0)
            plan.phases[phase].allocated += bonus
            plan.phases[phase].remaining += bonus

        # Mark source as fully used
        source.remaining = 0
        plan.reallocation_count += 1

        return plan

    def get_phase_budget(
        self,
        plan: BudgetPlan,
        phase: int,
    ) -> int:
        """Get available budget for a phase.

        Args:
            plan: Current budget plan
            phase: Phase number

        Returns:
            Available tokens for the phase
        """
        if phase not in plan.phases:
            return 0
        return plan.phases[phase].remaining

    def estimate_remaining_capacity(
        self,
        plan: BudgetPlan,
        current_phase: int,
    ) -> dict[str, Any]:
        """Estimate remaining research capacity.

        Args:
            plan: Current budget plan
            current_phase: Current phase number

        Returns:
            Capacity estimation dictionary
        """
        remaining_phases = [p for p in plan.phases.keys() if p >= current_phase]

        remaining_budget = sum(plan.phases[p].remaining for p in remaining_phases)

        # Estimate research depth (assuming ~500 tokens per finding)
        estimated_findings = remaining_budget // 500

        return {
            "remaining_phases": len(remaining_phases),
            "remaining_budget": remaining_budget,
            "synthesis_reserve": plan.synthesis_reserve,
            "estimated_findings_capacity": estimated_findings,
            "utilization_so_far": plan.overall_utilization,
        }

    def suggest_optimization(
        self,
        plan: BudgetPlan,
    ) -> list[str]:
        """Suggest budget optimizations.

        Args:
            plan: Current budget plan

        Returns:
            List of optimization suggestions
        """
        suggestions = []

        # Check for underutilization
        for phase, alloc in plan.phases.items():
            if alloc.status == "completed":
                utilization = alloc.used / max(alloc.allocated, 1)
                if utilization < 0.5:
                    suggestions.append(
                        f"Phase {phase} only used {utilization:.0%} of budget. Consider reducing allocation."
                    )
                elif utilization > 0.95:
                    suggestions.append(f"Phase {phase} nearly exhausted budget. Consider increasing allocation.")

        # Check overall utilization
        if plan.overall_utilization > 0.9:
            suggestions.append("Overall utilization high. Consider increasing total budget or reducing phase count.")
        elif plan.overall_utilization < 0.3:
            suggestions.append("Overall utilization low. Budget may be oversized for this research.")

        return suggestions

    def _get_weights_for_strategy(
        self,
        num_phases: int,
        strategy: AllocationStrategy,
    ) -> dict[int, float]:
        """Get phase weights for a strategy.

        Args:
            num_phases: Number of phases
            strategy: Allocation strategy

        Returns:
            Dictionary of phase -> weight
        """
        weights = {}

        if strategy == AllocationStrategy.EQUAL:
            for phase in range(1, num_phases + 1):
                weights[phase] = 1.0 / num_phases

        elif strategy == AllocationStrategy.FRONT_LOADED:
            # More for early phases (foundation)
            for phase in range(1, num_phases + 1):
                weights[phase] = (num_phases - phase + 1) / sum(range(1, num_phases + 1))

        elif strategy == AllocationStrategy.BACK_LOADED:
            # More for later phases (synthesis)
            for phase in range(1, num_phases + 1):
                weights[phase] = phase / sum(range(1, num_phases + 1))

        elif strategy == AllocationStrategy.WEIGHTED:
            # Default balanced weights with slight front-loading
            for phase in range(1, num_phases + 1):
                if phase == 1:
                    weights[phase] = 0.2
                elif phase == num_phases:
                    weights[phase] = 0.25
                else:
                    weights[phase] = 0.55 / max(num_phases - 2, 1)

        else:
            # Fallback to equal
            for phase in range(1, num_phases + 1):
                weights[phase] = 1.0 / num_phases

        return weights


class BudgetTracker:
    """Tracks budget usage across a session.

    Provides real-time budget monitoring and alerts.
    """

    def __init__(self, plan: BudgetPlan):
        """Initialize tracker with a plan.

        Args:
            plan: Budget plan to track
        """
        self.plan = plan
        self.usage_log: list[dict[str, Any]] = []
        self.alerts: list[str] = []

    def log_usage(
        self,
        phase: int,
        operation: str,
        tokens: int,
    ):
        """Log a token usage event.

        Args:
            phase: Phase number
            operation: Operation description
            tokens: Tokens used
        """
        self.usage_log.append(
            {
                "timestamp": _utc_now().isoformat(),
                "phase": phase,
                "operation": operation,
                "tokens": tokens,
            }
        )

        # Check for alerts
        if phase in self.plan.phases:
            alloc = self.plan.phases[phase]
            if alloc.used > alloc.allocated * 0.9:
                self.alerts.append(f"Phase {phase} at {alloc.used / alloc.allocated:.0%} capacity")

    def get_usage_summary(self) -> dict[str, Any]:
        """Get usage summary.

        Returns:
            Summary dictionary
        """
        return {
            "plan": self.plan.to_dict(),
            "usage_events": len(self.usage_log),
            "total_logged_tokens": sum(e["tokens"] for e in self.usage_log),
            "alerts": self.alerts,
        }
