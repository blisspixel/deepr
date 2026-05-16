"""Property-based tests for MCP client budget propagator.

Feature: mcp-client-agent-interop
- Property 6: Budget check correctness
- Property 7: Budget recording decreases remaining budget
- Property 8: Budget parameter is minimum of per-call limit and remaining
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from deepr.mcp.client.budget_propagator import BudgetPropagator
from deepr.mcp.client.profile import MCPClientProfile

# --- Test doubles ---


class FakeBudgetManager:
    """Fake budget manager for testing."""

    def __init__(self, remaining: float = 10.0) -> None:
        self.remaining = remaining

    def get_remaining_budget(self) -> float:
        return self.remaining


class FakeCostLedger:
    """Fake cost ledger that records events."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def record_event(
        self,
        profile_name: str,
        tool_name: str,
        cost: float,
        trace_id: str,
    ) -> None:
        self.events.append(
            {
                "profile_name": profile_name,
                "tool_name": tool_name,
                "cost": cost,
                "trace_id": trace_id,
            }
        )


# --- Strategies ---

positive_costs = st.floats(min_value=0.01, max_value=100.0, allow_nan=False, allow_infinity=False)
non_negative_costs = st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
budget_limits = st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False)
session_budgets = st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)


# Feature: mcp-client-agent-interop, Property 6: Budget check correctness


@settings(max_examples=200)
@given(
    estimated_cost=positive_costs,
    session_remaining=session_budgets,
    per_call_limit=budget_limits,
)
def test_property_6_budget_check_correctness(
    estimated_cost: float,
    session_remaining: float,
    per_call_limit: float,
) -> None:
    """For any estimated cost, remaining session budget, and per-call budget limit,
    check_budget() SHALL allow the call if and only if estimated_cost <= remaining_budget
    AND estimated_cost <= per_call_limit (when limit > 0). When denied, shortfall SHALL
    equal estimated_cost - min(remaining_budget, per_call_limit).

    **Validates: Requirements 3.1, 3.2, 3.4**
    """
    manager = FakeBudgetManager(remaining=session_remaining)
    ledger = FakeCostLedger()
    propagator = BudgetPropagator(budget_manager=manager, cost_ledger=ledger)

    profile = MCPClientProfile(name="test-server", command="test", budget_limit=per_call_limit)

    decision = propagator.check_budget(profile, estimated_cost, session_remaining)

    # Determine expected outcome
    if per_call_limit > 0:
        effective_cap = min(session_remaining, per_call_limit)
    else:
        effective_cap = session_remaining

    expected_allowed = estimated_cost <= effective_cap

    assert decision.allowed == expected_allowed
    assert decision.estimated_cost == estimated_cost
    assert decision.remaining_budget == session_remaining

    if not decision.allowed:
        expected_shortfall = estimated_cost - effective_cap
        assert abs(decision.shortfall - expected_shortfall) < 1e-9


# Feature: mcp-client-agent-interop, Property 7: Budget recording decreases remaining budget


@settings(max_examples=100)
@given(
    actual_cost=positive_costs,
    profile_name=st.from_regex(r"[a-z][a-z0-9\-]{0,10}", fullmatch=True),
    tool_name=st.from_regex(r"[a-z_]{1,15}", fullmatch=True),
    trace_id=st.from_regex(r"[a-f0-9]{8,16}", fullmatch=True),
)
def test_property_7_budget_recording(
    actual_cost: float,
    profile_name: str,
    tool_name: str,
    trace_id: str,
) -> None:
    """For any positive cost value recorded via record_cost(), the CostLedger SHALL
    contain a new event with that cost value.

    **Validates: Requirements 3.3**
    """
    manager = FakeBudgetManager(remaining=10.0)
    ledger = FakeCostLedger()
    propagator = BudgetPropagator(budget_manager=manager, cost_ledger=ledger)

    initial_count = len(ledger.events)
    propagator.record_cost(profile_name, tool_name, actual_cost, trace_id)

    # Ledger should have one new event
    assert len(ledger.events) == initial_count + 1

    # The event should contain the correct cost
    event = ledger.events[-1]
    assert event["cost"] == actual_cost
    assert event["profile_name"] == profile_name
    assert event["tool_name"] == tool_name
    assert event["trace_id"] == trace_id


# Feature: mcp-client-agent-interop, Property 8: Budget parameter is minimum of per-call limit and remaining


@settings(max_examples=200)
@given(
    per_call_limit=st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False),
    session_remaining=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
)
def test_property_8_budget_param_is_minimum(
    per_call_limit: float,
    session_remaining: float,
) -> None:
    """For any profile with max_budget_per_call > 0 and any remaining session budget,
    the budget parameter SHALL equal min(max_budget_per_call, remaining_budget).
    When budget_limit is 0, returns session_remaining.

    **Validates: Requirements 3.5**
    """
    manager = FakeBudgetManager(remaining=session_remaining)
    ledger = FakeCostLedger()
    propagator = BudgetPropagator(budget_manager=manager, cost_ledger=ledger)

    profile = MCPClientProfile(name="test-server", command="test", budget_limit=per_call_limit)

    result = propagator.get_budget_param(profile, session_remaining)

    if per_call_limit > 0:
        expected = min(per_call_limit, session_remaining)
    else:
        expected = session_remaining

    assert abs(result - expected) < 1e-9
