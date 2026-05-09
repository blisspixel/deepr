"""Budget propagation for outbound MCP tool calls.

Enforces per-call and session budget limits before dispatching external
tool calls, and records actual costs after completion.

Feature: mcp-client-agent-interop
"""

from __future__ import annotations

import logging
from typing import Protocol

from deepr.mcp.client.errors import BudgetDecision
from deepr.mcp.client.profile import MCPClientProfile

logger = logging.getLogger(__name__)


class BudgetManagerProtocol(Protocol):
    """Protocol for reading remaining session budget."""

    def get_remaining_budget(self) -> float:
        """Return the remaining budget for the current session."""
        ...


class CostLedgerProtocol(Protocol):
    """Protocol for recording cost events."""

    def record_event(
        self,
        profile_name: str,
        tool_name: str,
        cost: float,
        trace_id: str,
    ) -> None:
        """Record a cost event to the ledger."""
        ...


class BudgetPropagator:
    """Enforce budget limits on outbound MCP tool calls.

    Checks estimated costs against session and per-call limits before
    dispatch, and records actual costs to the ledger after completion.

    Usage::

        propagator = BudgetPropagator(
            budget_manager=my_budget_manager,
            cost_ledger=my_cost_ledger,
        )
        decision = propagator.check_budget(profile, estimated_cost=0.5, session_remaining=2.0)
        if decision.allowed:
            # dispatch the call...
            propagator.record_cost("server", "tool", actual_cost=0.3, trace_id="abc")
    """

    def __init__(
        self,
        budget_manager: BudgetManagerProtocol,
        cost_ledger: CostLedgerProtocol,
    ) -> None:
        self._budget_manager = budget_manager
        self._cost_ledger = cost_ledger
        self._remaining_overrides: dict[str, float] = {}

    def check_budget(
        self,
        profile: MCPClientProfile,
        estimated_cost: float,
        session_remaining: float,
    ) -> BudgetDecision:
        """Check if a call is within budget constraints.

        Allow the call if and only if:
        - estimated_cost <= session_remaining
        - estimated_cost <= per_call_limit (when budget_limit > 0)

        When denied, shortfall = estimated_cost - min(remaining, limit).
        """
        per_call_limit = profile.budget_limit

        # Determine the effective cap
        if per_call_limit > 0:
            effective_cap = min(session_remaining, per_call_limit)
        else:
            effective_cap = session_remaining

        if estimated_cost <= effective_cap:
            return BudgetDecision(
                allowed=True,
                reason="Within budget",
                remaining_budget=session_remaining,
                estimated_cost=estimated_cost,
                shortfall=0.0,
            )

        shortfall = estimated_cost - effective_cap
        if per_call_limit > 0 and per_call_limit < session_remaining:
            reason = (
                f"Estimated cost {estimated_cost:.2f} exceeds "
                f"per-call limit {per_call_limit:.2f}"
            )
        else:
            reason = (
                f"Estimated cost {estimated_cost:.2f} exceeds "
                f"remaining budget {session_remaining:.2f}"
            )

        return BudgetDecision(
            allowed=False,
            reason=reason,
            remaining_budget=session_remaining,
            estimated_cost=estimated_cost,
            shortfall=shortfall,
        )

    def record_cost(
        self,
        profile_name: str,
        tool_name: str,
        actual_cost: float,
        trace_id: str,
    ) -> None:
        """Record actual cost from a tool response.

        Writes to the cost ledger and decreases the tracked remaining budget.
        """
        self._cost_ledger.record_event(
            profile_name=profile_name,
            tool_name=tool_name,
            cost=actual_cost,
            trace_id=trace_id,
        )
        logger.debug(
            "Recorded cost %.4f for %s/%s (trace=%s)",
            actual_cost,
            profile_name,
            tool_name,
            trace_id,
        )

    def get_budget_param(
        self,
        profile: MCPClientProfile,
        session_remaining: float,
    ) -> float:
        """Calculate budget parameter to pass to an external tool.

        Returns min(max_budget_per_call, remaining_budget).
        When budget_limit is 0 (unlimited per-call), returns session_remaining.
        """
        per_call_limit = profile.budget_limit
        if per_call_limit > 0:
            return min(per_call_limit, session_remaining)
        return session_remaining
