"""Property tests for MCP provider resources.

Feature: mcp-client-agent-interop
Properties: 19, 20, 21
Validates: Requirements 9.2, 9.3, 9.4
"""

from __future__ import annotations

from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from deepr.mcp.provider.resources import ResourceHandler

# --- Mock implementations ---

class MockExpertState:
    """Mock expert state for testing."""

    def __init__(self, experts: dict[str, dict[str, Any]]) -> None:
        self._experts = experts

    def get_expert_names(self) -> list[str]:
        return list(self._experts.keys())

    def get_knowledge(self, name: str) -> dict[str, Any]:
        expert = self._experts.get(name, {})
        return expert.get("knowledge", {})

    def get_gaps(self, name: str) -> list[dict[str, Any]]:
        expert = self._experts.get(name, {})
        return expert.get("gaps", [])


class MockCostState:
    """Mock cost state for testing."""

    def __init__(
        self,
        daily: float = 0.0,
        monthly: float = 0.0,
        remaining: float = 0.0,
        active_jobs: int = 0,
    ) -> None:
        self._daily = daily
        self._monthly = monthly
        self._remaining = remaining
        self._active_jobs = active_jobs

    def get_daily_spend(self) -> float:
        return self._daily

    def get_monthly_spend(self) -> float:
        return self._monthly

    def get_remaining_budget(self) -> float:
        return self._remaining

    def get_active_job_count(self) -> int:
        return self._active_jobs


# --- Strategies ---

confidence_st = st.floats(min_value=0.0, max_value=1.0)
claim_count_st = st.integers(min_value=0, max_value=1000)
priority_st = st.floats(min_value=0.0, max_value=10.0, allow_nan=False)
spend_st = st.floats(min_value=0.0, max_value=1000.0, allow_nan=False)


# --- Property 19: Expert knowledge resource accuracy ---

@settings(max_examples=100)
@given(
    claim_count=claim_count_st,
    avg_confidence=confidence_st,
    last_updated=st.text(min_size=5, max_size=20),
)
def test_expert_knowledge_resource_accuracy(
    claim_count: int,
    avg_confidence: float,
    last_updated: str,
) -> None:
    """Property 19: Expert knowledge resource accuracy.

    For any expert with a known belief state, the knowledge resource
    returns correct claim_count, average_confidence, and last_updated.

    **Validates: Requirements 9.2**
    """
    knowledge = {
        "claim_count": claim_count,
        "average_confidence": avg_confidence,
        "last_updated": last_updated,
    }
    state = MockExpertState({"analyst": {"knowledge": knowledge}})
    handler = ResourceHandler(expert_state=state)

    result = handler.handle("deepr://experts/analyst/knowledge")

    assert result is not None
    assert result.content["claim_count"] == claim_count
    assert result.content["average_confidence"] == avg_confidence
    assert result.content["last_updated"] == last_updated


# --- Property 20: Expert gaps resource ordering ---

@settings(max_examples=100)
@given(
    priorities=st.lists(priority_st, min_size=1, max_size=10),
)
def test_expert_gaps_resource_ordering(priorities: list[float]) -> None:
    """Property 20: Expert gaps resource ordering.

    For any expert with knowledge gaps, the gaps resource returns
    gaps sorted by priority score in descending order.

    **Validates: Requirements 9.3**
    """
    gaps = [
        {"description": f"Gap {i}", "category": "infrastructure", "priority": p}
        for i, p in enumerate(priorities)
    ]
    state = MockExpertState({"analyst": {"gaps": gaps}})
    handler = ResourceHandler(expert_state=state)

    result = handler.handle("deepr://experts/analyst/gaps")

    assert result is not None
    result_priorities = [g["priority"] for g in result.content]

    # Verify descending order
    for i in range(len(result_priorities) - 1):
        assert result_priorities[i] >= result_priorities[i + 1], (
            f"Gaps not sorted descending: {result_priorities}"
        )


# --- Property 21: Cost summary resource accuracy ---

@settings(max_examples=100)
@given(
    daily=spend_st,
    monthly=spend_st,
    remaining=spend_st,
    active_jobs=st.integers(min_value=0, max_value=100),
)
def test_cost_summary_resource_accuracy(
    daily: float,
    monthly: float,
    remaining: float,
    active_jobs: int,
) -> None:
    """Property 21: Cost summary resource accuracy.

    For any cost ledger state, the costs/summary resource returns
    correct daily_spend, monthly_spend, remaining_budget, and active_job_count.

    **Validates: Requirements 9.4**
    """
    cost_state = MockCostState(
        daily=daily,
        monthly=monthly,
        remaining=remaining,
        active_jobs=active_jobs,
    )
    handler = ResourceHandler(cost_state=cost_state)

    result = handler.handle("deepr://costs/summary")

    assert result is not None
    assert result.content["daily_spend"] == daily
    assert result.content["monthly_spend"] == monthly
    assert result.content["remaining_budget"] == remaining
    assert result.content["active_job_count"] == active_jobs
