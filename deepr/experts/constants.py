"""Shared constants for the expert chat system."""

from __future__ import annotations

# Model used for cheap utility calls (plan decomposition, synthesis, follow-ups)
UTILITY_MODEL = "gpt-4o-mini"

# Tool names
TOOL_SEARCH_KB = "search_knowledge_base"
TOOL_STANDARD_RESEARCH = "standard_research"
TOOL_DEEP_RESEARCH = "deep_research"
TOOL_SKILL_CALL = "skill_tool_call"

ALL_TOOL_NAMES = frozenset({TOOL_SEARCH_KB, TOOL_STANDARD_RESEARCH, TOOL_DEEP_RESEARCH, TOOL_SKILL_CALL})

# Human-readable tool descriptions
TOOL_DESCRIPTIONS: dict[str, str] = {
    TOOL_SEARCH_KB: "Search expert's documents (free)",
    TOOL_STANDARD_RESEARCH: "Web search via Grok (free)",
    TOOL_DEEP_RESEARCH: "Deep analysis ($0.10-0.30)",
}

# Budget constants
SYNTHESIS_BUDGET_FRACTION = 0.1  # 10% of budget reserved for synthesis
