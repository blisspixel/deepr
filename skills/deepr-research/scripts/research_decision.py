"""Non-authoritative prompt-shape routing for the bundled Deepr skill.

Lexical and length signals may suggest how to frame a preview. They never select
a paid model, estimate a provider envelope, or authorize dispatch. Call Deepr's
current exact preview for those decisions.
"""

from dataclasses import dataclass
from enum import Enum
from math import isfinite


class ResearchMode(Enum):
    """Prompt-shape hints with no execution or cost authority."""

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
        if not isfinite(self.max_cost):
            return "EXACT PREVIEW REQUIRED"
        if self.min_cost == 0 and self.max_cost == 0:
            return "FREE"
        if self.min_cost == self.max_cost:
            return f"${self.min_cost:.2f}"
        return f"${self.min_cost:.2f}-${self.max_cost:.2f}"

    @property
    def time_range(self) -> str:
        if self.min_time_seconds <= 0 or self.max_time_seconds <= 0:
            return "UNKNOWN"
        if self.max_time_seconds < 60:
            return f"{self.min_time_seconds}-{self.max_time_seconds} sec"
        min_min = self.min_time_seconds // 60
        max_min = self.max_time_seconds // 60
        if min_min == max_min:
            return f"{min_min} min"
        return f"{min_min}-{max_min} min"


@dataclass(frozen=True)
class ResearchDecision:
    """A routing hint that requires an exact preview before execution."""

    mode: ResearchMode
    model: str
    cost: CostEstimate
    rationale: str
    confidence: float  # 0.0 to 1.0


# No static table can safely authorize a current provider request. Infinity
# keeps every paid-looking hint confirmation-required until exact preview.
MODE_COSTS: dict[ResearchMode, CostEstimate] = {mode: CostEstimate(0.0, float("inf"), 0, 0) for mode in ResearchMode}

MODE_MODELS: dict[ResearchMode, str] = {mode: "explicit-model-required" for mode in ResearchMode}

# Query complexity indicators
DEEP_INDICATORS = frozenset(
    {
        "comprehensive",
        "thorough",
        "detailed",
        "in-depth",
        "exhaustive",
        "analyze",
        "compare",
        "evaluate",
        "assess",
        "investigate",
        "market research",
        "competitive analysis",
        "due diligence",
        "strategic",
        "long-term",
        "implications",
        "trends",
    }
)

QUICK_INDICATORS = frozenset(
    {
        "what is",
        "define",
        "quick",
        "brief",
        "simple",
        "lookup",
        "find",
        "check",
        "verify",
        "confirm",
    }
)


def classify_query(
    query: str,
    *,
    force_mode: ResearchMode | None = None,
    max_budget: float | None = None,
) -> ResearchDecision:
    """
    Return a non-authoritative prompt-shape hint.

    Query length and lexical signals only route a future preview. They cannot
    decide semantic complexity, model suitability, cost, or dispatch.

    Args:
        query: The research query text (must be non-empty)
        force_mode: Override automatic classification with specific mode
        max_budget: Validated for form only; exact preview owns budget fit

    Returns:
        ResearchDecision with an unknown cost envelope and explicit-model marker

    Raises:
        ValueError: If query is empty or max_budget is negative

    Example:
        >>> decision = classify_query("What is Python?")
        >>> decision.mode
        ResearchMode.QUICK
        >>> decision.cost.cost_range
        'EXACT PREVIEW REQUIRED'
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
    """Retain the hint because only exact preview can evaluate budget fit."""
    del max_budget
    return mode


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

    reasons.append("routing hint only; exact provider preview required")
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
    """Return an intentionally unknown envelope that cannot authorize spend."""
    return MODE_COSTS[mode]


def requires_confirmation(decision: ResearchDecision, threshold: float = 5.0) -> bool:
    """Require confirmation until an exact provider preview replaces the hint."""
    return decision.cost.max_cost >= threshold
