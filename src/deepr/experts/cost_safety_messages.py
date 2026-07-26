"""Cost estimates and operator-facing pause messages."""

from __future__ import annotations


def estimate_curriculum_cost(
    topic_count: int,
    deep_research_count: int = 0,
    quick_research_count: int = 0,
    docs_count: int = 0,
) -> dict[str, float | int]:
    """Estimate the bounded cost range of a learning curriculum."""
    deep_cost = 2.00
    quick_cost = 0.25
    docs_cost = 0.15
    other_count = max(0, topic_count - deep_research_count - quick_research_count - docs_count)
    expected = (
        deep_research_count * deep_cost
        + quick_research_count * quick_cost
        + docs_count * docs_cost
        + other_count * quick_cost
    )
    return {
        "expected_cost": expected,
        "min_cost": expected * 0.5,
        "max_cost": expected * 1.5,
        "topic_count": topic_count,
    }


def format_cost_warning(expected_cost: float, budget_limit: float | None) -> str:
    """Format a human-readable cost warning for curriculum execution."""
    message = f"Estimated cost: ${expected_cost:.2f}"
    if budget_limit is None:
        return message
    if expected_cost > budget_limit:
        return message + f" (exceeds ${budget_limit:.2f} budget - will stop at limit)"
    return message + f" (within ${budget_limit:.2f} budget)"


def is_pausable_limit(reason: str) -> bool:
    """Return whether a window limit can resume automatically later."""
    lowered = reason.lower() if reason else ""
    return any(window in lowered for window in ("daily", "weekly", "monthly"))


def get_resume_message(reason: str) -> str:
    """Explain when a window-limited operation can resume."""
    lowered = (reason or "").lower()
    if "daily" in lowered:
        return "Daily spending limit reached. Learning will resume tomorrow."
    if "weekly" in lowered:
        return "Weekly spending limit reached. Learning will resume next week."
    if "monthly" in lowered:
        return "Monthly spending limit reached. Learning will resume next month."
    return f"Spending limit reached: {reason}"
