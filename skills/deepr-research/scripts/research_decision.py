"""
Research mode classification and cost estimation.

This module determines the optimal research mode based on query characteristics
and provides cost/time estimates for informed decision-making.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import re


class ResearchMode(Enum):
    """Available research modes with increasing depth and cost."""
    QUICK = "quick"
    STANDARD = "standard"
    DEEP_FAST = "deep_fast"
    DEEP_PREMIUM = "deep_premium"


@dataclass(frozen=True)
class CostEstimate:
    """Cost and time estimates for a research operation."""
    min_cost: float
    max_cost: float
    min_time_seconds: int
    max_time_seconds: int
    
    @property
    def cost_range(self) -> str:
        if self.min_cost == 0 and self.max_cost == 0:
            return "FREE"
        if self.min_cost == self.max_cost:
            return f"${self.min_cost:.2f}"
        return f"${self.min_cost:.2f}-${self.max_cost:.2f}"
    
    @property
    def time_range(self) -> str:
        if self.max_time_seconds < 60:
            return f"{self.min_time_seconds}-{self.max_time_seconds} sec"
        min_min = self.min_time_seconds // 60
        max_min = self.max_time_seconds // 60
        if min_min == max_min:
            return f"{min_min} min"
        return f"{min_min}-{max_min} min"


@dataclass(frozen=True)
class ResearchDecision:
    """Complete recommendation for a research query."""
    mode: ResearchMode
    model: str
    cost: CostEstimate
    rationale: str
    confidence: float  # 0.0 to 1.0


# Cost tables by mode
MODE_COSTS: dict[ResearchMode, CostEstimate] = {
    ResearchMode.QUICK: CostEstimate(0, 0, 1, 5),
    ResearchMode.STANDARD: CostEstimate(0.001, 0.005, 30, 60),
    ResearchMode.DEEP_FAST: CostEstimate(0.10, 0.30, 300, 600),
    ResearchMode.DEEP_PREMIUM: CostEstimate(0.50, 0.50, 600, 1200),
}

MODE_MODELS: dict[ResearchMode, str] = {
    ResearchMode.QUICK: "grok-4-fast",
    ResearchMode.STANDARD: "grok-4-fast",
    ResearchMode.DEEP_FAST: "o4-mini",
    ResearchMode.DEEP_PREMIUM: "o3",
}

# Query complexity indicators
DEEP_INDICATORS = frozenset({
    "comprehensive", "thorough", "detailed", "in-depth", "exhaustive",
    "analyze", "compare", "evaluate", "assess", "investigate",
    "market research", "competitive analysis", "due diligence",
    "strategic", "long-term", "implications", "trends",
})

QUICK_INDICATORS = frozenset({
    "what is", "define", "quick", "brief", "simple",
    "lookup", "find", "check", "verify", "confirm",
})


def classify_query(
    query: str,
    *,
    force_mode: Optional[ResearchMode] = None,
    max_budget: Optional[float] = None,
) -> ResearchDecision:
    """
    Classify a research query and recommend optimal mode.
    
    Analyzes query characteristics (length, keywords, complexity) to
    determine the most appropriate research mode and provides cost/time
    estimates.
    
    Args:
        query: The research query text (must be non-empty)
        force_mode: Override automatic classification with specific mode
        max_budget: Maximum budget constraint in dollars (must be non-negative)
    
    Returns:
        ResearchDecision with mode, cost estimate, and rationale
    
    Raises:
        ValueError: If query is empty or max_budget is negative
    
    Example:
        >>> decision = classify_query("What is Python?")
        >>> decision.mode
        ResearchMode.QUICK
        >>> decision.cost.cost_range
        'FREE'
    """
    # Validate query
    if not query or not query.strip():
        raise ValueError("Query cannot be empty")
    
    # Validate budget
    if max_budget is not None and max_budget < 0:
        raise ValueError("max_budget cannot be negative")
    
    query_lower = query.lower().strip()
    query_words = set(query_lower.split())
    query_len = len(query_lower)
    
    # Handle forced mode
    if force_mode is not None:
        return _build_decision(
            force_mode,
            f"Mode forced to {force_mode.value}",
            confidence=1.0,
        )
    
    # Score each mode based on query characteristics
    scores = _score_query(query_lower, query_words, query_len)
    
    # Select best mode
    best_mode = max(scores, key=scores.get)
    confidence = scores[best_mode]
    
    # Apply budget constraint
    if max_budget is not None:
        best_mode = _apply_budget_constraint(best_mode, max_budget)
    
    rationale = _generate_rationale(query_lower, best_mode, scores)
    
    return _build_decision(best_mode, rationale, confidence)


def _score_query(
    query_lower: str,
    query_words: set[str],
    query_len: int,
) -> dict[ResearchMode, float]:
    """Score each mode based on query characteristics."""
    scores = {mode: 0.0 for mode in ResearchMode}
    
    # Keyword-based scoring (check first - higher priority)
    deep_matches = sum(1 for ind in DEEP_INDICATORS if ind in query_lower)
    quick_matches = sum(1 for ind in QUICK_INDICATORS if ind in query_lower)
    
    # Deep indicators have strong weight
    scores[ResearchMode.DEEP_FAST] += deep_matches * 0.25
    scores[ResearchMode.DEEP_PREMIUM] += deep_matches * 0.15
    scores[ResearchMode.STANDARD] += deep_matches * 0.1
    
    # Quick indicators
    scores[ResearchMode.QUICK] += quick_matches * 0.2
    
    # Length-based scoring (secondary factor)
    if query_len < 50 and deep_matches == 0:
        scores[ResearchMode.QUICK] += 0.2
    elif query_len < 150:
        scores[ResearchMode.STANDARD] += 0.15
    else:
        scores[ResearchMode.DEEP_FAST] += 0.15
        scores[ResearchMode.DEEP_PREMIUM] += 0.1
    
    # Question complexity
    if query_lower.count("?") > 1:
        scores[ResearchMode.DEEP_FAST] += 0.15
    
    # Multi-part queries
    if " and " in query_lower or " vs " in query_lower:
        scores[ResearchMode.STANDARD] += 0.1
        scores[ResearchMode.DEEP_FAST] += 0.1
    
    # Ensure at least one mode has a score
    if all(s == 0 for s in scores.values()):
        scores[ResearchMode.STANDARD] = 0.5
    
    # Normalize scores
    total = sum(scores.values()) or 1.0
    return {mode: score / total for mode, score in scores.items()}


def _apply_budget_constraint(
    mode: ResearchMode,
    max_budget: float,
) -> ResearchMode:
    """Downgrade mode if it exceeds budget."""
    mode_order = [
        ResearchMode.QUICK,
        ResearchMode.STANDARD,
        ResearchMode.DEEP_FAST,
        ResearchMode.DEEP_PREMIUM,
    ]
    
    current_idx = mode_order.index(mode)
    
    for idx in range(current_idx, -1, -1):
        candidate = mode_order[idx]
        if MODE_COSTS[candidate].max_cost <= max_budget:
            return candidate
    
    return ResearchMode.QUICK


def _generate_rationale(
    query_lower: str,
    mode: ResearchMode,
    scores: dict[ResearchMode, float],
) -> str:
    """Generate human-readable rationale for mode selection."""
    reasons = []
    
    if mode == ResearchMode.QUICK:
        if any(ind in query_lower for ind in QUICK_INDICATORS):
            reasons.append("Query indicates simple lookup")
        if len(query_lower) < 50:
            reasons.append("Short query length")
    
    elif mode == ResearchMode.STANDARD:
        reasons.append("Moderate complexity detected")
        if " and " in query_lower or " vs " in query_lower:
            reasons.append("Multi-part comparison")
    
    elif mode in (ResearchMode.DEEP_FAST, ResearchMode.DEEP_PREMIUM):
        if any(ind in query_lower for ind in DEEP_INDICATORS):
            reasons.append("Deep analysis keywords detected")
        if len(query_lower) > 150:
            reasons.append("Complex query structure")
    
    if not reasons:
        reasons.append("Default classification based on query characteristics")
    
    return "; ".join(reasons)


def _build_decision(
    mode: ResearchMode,
    rationale: str,
    confidence: float,
) -> ResearchDecision:
    """Build complete decision object."""
    return ResearchDecision(
        mode=mode,
        model=MODE_MODELS[mode],
        cost=MODE_COSTS[mode],
        rationale=rationale,
        confidence=min(1.0, max(0.0, confidence)),
    )


def estimate_cost(mode: ResearchMode) -> CostEstimate:
    """Get cost estimate for a specific mode."""
    return MODE_COSTS[mode]


def requires_confirmation(decision: ResearchDecision, threshold: float = 5.0) -> bool:
    """Check if decision requires user confirmation based on cost."""
    return decision.cost.max_cost >= threshold
