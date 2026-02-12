"""EV/cost ranking for knowledge gaps.

Scores gaps by expected value relative to estimated research cost,
enabling prioritized gap-filling decisions.
"""

from deepr.core.contracts import Gap

# Cost lookup by domain velocity
_VELOCITY_COSTS = {
    "fast": 0.25,
    "medium": 1.00,
    "slow": 2.00,
}


def score_gap(gap: Gap, domain_velocity: str = "medium") -> Gap:
    """Populate ev_cost_ratio on a Gap.

    Formula:
        base_value = priority / 5.0
        frequency_boost = min(times_asked / 10, 0.3)
        expected_value = min(base_value + frequency_boost, 1.0)
        estimated_cost = lookup from domain_velocity
        ev_cost_ratio = expected_value / max(estimated_cost, 0.001)

    Args:
        gap: Gap to score (modified in place and returned)
        domain_velocity: "fast", "medium", or "slow"

    Returns:
        The same Gap with expected_value, estimated_cost, and ev_cost_ratio set.
    """
    base_value = gap.priority / 5.0
    frequency_boost = min(gap.times_asked / 10, 0.3)
    expected_value = min(base_value + frequency_boost, 1.0)

    estimated_cost = _VELOCITY_COSTS.get(domain_velocity, 1.00)

    gap.expected_value = expected_value
    gap.estimated_cost = estimated_cost
    gap.ev_cost_ratio = expected_value / max(estimated_cost, 0.001)

    return gap


def rank_gaps(gaps: list[Gap], top_n: int = 5) -> list[Gap]:
    """Return top N gaps by ev_cost_ratio descending.

    Args:
        gaps: List of scored gaps
        top_n: Maximum number to return

    Returns:
        Sorted list of up to top_n gaps
    """
    return sorted(gaps, key=lambda g: g.ev_cost_ratio, reverse=True)[:top_n]
