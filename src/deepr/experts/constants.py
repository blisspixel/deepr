"""Shared constants for the expert chat system."""

from __future__ import annotations

# Model used for cheap utility calls (plan decomposition, synthesis, follow-ups)
UTILITY_MODEL = "gpt-5.6-luna"

# Autonomous learning research models (docs/design/model-lifecycle-2026-10-27.md).
LEARN_FOCUS_MODEL = "gpt-5.6-terra"
LEARN_CAMPAIGN_MODEL = "gpt-5.6-sol"


def learn_topic_cost(model: str) -> float:
    """Per-topic estimate taken from the registry, never an invented rate."""
    from deepr.providers.registry import get_cost_estimate

    return get_cost_estimate(model)


# Tool names
TOOL_SEARCH_KB = "search_knowledge_base"
TOOL_STANDARD_RESEARCH = "standard_research"
TOOL_DEEP_RESEARCH = "deep_research"
TOOL_SKILL_CALL = "skill_tool_call"

ALL_TOOL_NAMES = frozenset({TOOL_SEARCH_KB, TOOL_STANDARD_RESEARCH, TOOL_DEEP_RESEARCH, TOOL_SKILL_CALL})

# Human-readable tool descriptions
TOOL_DESCRIPTIONS: dict[str, str] = {
    TOOL_SEARCH_KB: "Search configured expert knowledge",
    TOOL_STANDARD_RESEARCH: "Web research (metered calls blocked)",
    TOOL_DEEP_RESEARCH: "Deep analysis (metered calls blocked)",
}

# Budget constants
SYNTHESIS_BUDGET_FRACTION = 0.1  # 10% of budget reserved for synthesis

# Concurrency limits for bounded fan-out
MAX_COUNCIL_CONCURRENCY = 5  # Max parallel experts in council consultation
MAX_PLAN_CONCURRENCY = 4  # Max parallel steps in task plan execution
