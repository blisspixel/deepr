"""Cost estimation, tracking, and control for research operations."""

import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from typing import Any

logger = logging.getLogger(__name__)


def _validated_money(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a finite non-negative number")
    numeric = float(value)
    if not isfinite(numeric) or numeric < 0:
        raise ValueError(f"{field_name} must be a finite non-negative number")
    return numeric


@dataclass
class CostEstimate:
    """Estimated cost for a research operation."""

    min_cost: float
    max_cost: float
    expected_cost: float
    model: str
    reasoning: str


@dataclass
class CostRecord:
    """Actual cost record for a completed research operation."""

    job_id: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    total_tokens: int
    cost: float
    timestamp: datetime


class CostEstimator:
    """
    Estimate costs for research operations.

    Deep Research is EXPENSIVE - always estimate before running.
    """

    # DEPRECATED: kept only for backward compatibility with external callers.
    # Pricing lookups now go through deepr.providers.registry.get_token_pricing
    # (the single source of truth). This 4-model snapshot silently priced every
    # other model at o3-deep-research rates - e.g. a $10/$50 frontier model
    # would pass pre-flight at $2/$8.
    PRICING = {
        "o3-deep-research": {
            "input": 2.00,  # $2.00 per 1M input tokens
            "output": 8.00,  # $8.00 per 1M output tokens
        },
        "o4-mini-deep-research": {
            "input": 1.10,  # $1.10 per 1M input tokens
            "output": 4.40,  # $4.40 per 1M output tokens
        },
        "gpt-5": {
            "input": 0.05,  # GPT-5 reasoning model
            "output": 0.15,
        },
        "gpt-5-mini": {
            "input": 0.01,  # GPT-5-mini (fast reasoning)
            "output": 0.03,
        },
    }

    @staticmethod
    def _get_pricing(model: str, input_tokens: int | None = None) -> dict[str, float]:
        """Resolve per-1M-token pricing from the model registry.

        The registry handles alias resolution, normalization, longest-match,
        tiered pricing, and logs a warning for unknown models.
        """
        from deepr.providers.registry import get_token_pricing

        return get_token_pricing(model, input_tokens=input_tokens)

    @classmethod
    def estimate_prompt_tokens(cls, prompt: str, documents: list[Any] | None = None) -> int:
        """
        Rough estimation of token count.

        Rule of thumb: 1 token ≈ 4 characters
        """
        char_count = len(prompt)

        # Add document content estimation
        if documents:
            # Assume average document is 5000 tokens
            char_count += len(documents) * 20000

        return int(char_count / 4)

    @classmethod
    def estimate_cost(
        cls,
        prompt: str,
        model: str = "o3-deep-research",
        documents: list[Any] | None = None,
        enable_web_search: bool = True,
    ) -> CostEstimate:
        """
        Estimate cost for a research operation.

        WARNING: Deep Research models can be very expensive.
        Always review estimates before running.

        Args:
            prompt: Research prompt
            model: Model to use
            documents: List of documents (if any)
            enable_web_search: Whether web search is enabled

        Returns:
            Cost estimate with min/max/expected
        """
        # Estimate input tokens first so tiered-pricing models (Gemini 3.x
        # Pro above 200K input tokens) are estimated at the tier rate.
        input_tokens = cls.estimate_prompt_tokens(prompt, documents)

        # Get base model pricing from the registry (single source of truth)
        pricing = cls._get_pricing(model, input_tokens=input_tokens)

        # Deep Research models generate A LOT of output
        # Typical ranges:
        # - Short query: 5K-10K output tokens
        # - Medium query: 10K-25K output tokens
        # - Complex query: 25K-100K output tokens
        # - With web search: Add 50% more

        if "deep-research" in model:
            # Deep research generates extensive output
            if len(prompt) < 50:
                output_min, output_max = 5000, 15000
            elif len(prompt) < 200:
                output_min, output_max = 10000, 30000
            else:
                output_min, output_max = 25000, 100000

            if enable_web_search:
                output_min = int(output_min * 1.5)
                output_max = int(output_max * 1.5)

            output_expected = (output_min + output_max) // 2
        else:
            # Regular models
            output_min = input_tokens
            output_max = input_tokens * 3
            output_expected = input_tokens * 2

        # Calculate costs
        input_cost = (input_tokens / 1_000_000) * pricing["input"]

        output_cost_min = (output_min / 1_000_000) * pricing["output"]
        output_cost_max = (output_max / 1_000_000) * pricing["output"]
        output_cost_expected = (output_expected / 1_000_000) * pricing["output"]

        min_cost = input_cost + output_cost_min
        max_cost = input_cost + output_cost_max
        expected_cost = input_cost + output_cost_expected

        # Token arithmetic can be unrealistically tiny for short prompts and
        # does not include provider-side reasoning or tool work. The registry's
        # per-query estimate is the conservative admission floor. Keeping the
        # unrounded token estimate still matters for exact settlement.
        from deepr.providers.registry import get_cost_estimate

        per_query_floor = get_cost_estimate(model, input_tokens=input_tokens)
        if per_query_floor > max_cost:
            max_cost = per_query_floor

        # Reasoning
        reasoning_parts = [
            f"Estimated {input_tokens:,} input tokens (${input_cost:.4f})",
            f"Expected {output_expected:,} output tokens (${output_cost_expected:.4f})",
            f"Range: {output_min:,}-{output_max:,} output tokens",
        ]

        if enable_web_search:
            reasoning_parts.append("Web search enabled (increases output)")

        if documents:
            reasoning_parts.append(f"{len(documents)} documents attached")

        if per_query_floor > input_cost + output_cost_max:
            reasoning_parts.append(f"Registry per-query admission floor: ${per_query_floor:.6f}")

        return CostEstimate(
            min_cost=min_cost,
            max_cost=max_cost,
            expected_cost=expected_cost,
            model=model,
            reasoning=" | ".join(reasoning_parts),
        )

    @classmethod
    def calculate_actual_cost(
        cls,
        model: str,
        input_tokens: int,
        output_tokens: int,
        reasoning_tokens: int = 0,
    ) -> float:
        """
        Calculate actual cost from token usage.

        Args:
            model: Model used
            input_tokens: Input tokens consumed
            output_tokens: Output tokens consumed
            reasoning_tokens: Reasoning tokens (for o1/o3 models)

        Returns:
            Total cost in USD
        """
        pricing = cls._get_pricing(model, input_tokens=input_tokens)

        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]

        # Reasoning tokens typically billed at output rate
        reasoning_cost = (reasoning_tokens / 1_000_000) * pricing["output"]

        # Machine accounting stays unrounded. Human-facing output may format
        # this value, but rounding here can turn real micro-costs into $0 and
        # release a durable reservation without recording provider spend.
        return input_cost + output_cost + reasoning_cost


class CostController:
    """
    Control and limit research costs.

    Prevents accidental overspending.
    """

    def __init__(
        self,
        max_cost_per_job: float = 5.0,
        max_daily_cost: float = 25.0,
        max_monthly_cost: float = 200.0,
    ):
        """
        Initialize cost controller with limits.

        Args:
            max_cost_per_job: Maximum cost allowed for single job
            max_daily_cost: Maximum daily spending
            max_monthly_cost: Maximum monthly spending
        """
        self.max_cost_per_job = _validated_money(max_cost_per_job, field_name="max_cost_per_job")
        self.max_daily_cost = _validated_money(max_daily_cost, field_name="max_daily_cost")
        self.max_monthly_cost = _validated_money(max_monthly_cost, field_name="max_monthly_cost")

        self._lock = threading.Lock()
        self.daily_spending = 0.0
        self.monthly_spending = 0.0
        self.last_reset = datetime.now(UTC)

    def check_cost_limit(self, estimate: CostEstimate) -> tuple[bool, str | None]:
        """
        Check if operation would exceed cost limits.

        Args:
            estimate: Cost estimate for operation

        Returns:
            (allowed, reason) - reason is None if allowed
        """
        min_cost = _validated_money(estimate.min_cost, field_name="estimate.min_cost")
        max_cost = _validated_money(estimate.max_cost, field_name="estimate.max_cost")
        expected_cost = _validated_money(estimate.expected_cost, field_name="estimate.expected_cost")
        if not min_cost <= expected_cost <= max_cost:
            raise ValueError("cost estimate must satisfy min_cost <= expected_cost <= max_cost")
        self.reset_if_needed()

        # Check per-job limit
        if max_cost > self.max_cost_per_job:
            return False, (
                f"Job may cost ${max_cost:.2f}, exceeds limit of "
                f"${self.max_cost_per_job:.2f}. Use --cost-sensitive or reduce scope."
            )

        # Check daily limit
        if self.daily_spending + expected_cost > self.max_daily_cost:
            return False, (
                f"Daily spending (${self.daily_spending:.2f}) + estimated cost "
                f"(${expected_cost:.2f}) exceeds daily limit of "
                f"${self.max_daily_cost:.2f}"
            )

        # Check monthly limit
        if self.monthly_spending + expected_cost > self.max_monthly_cost:
            return False, (
                f"Monthly spending (${self.monthly_spending:.2f}) + estimated cost "
                f"(${expected_cost:.2f}) exceeds monthly limit of "
                f"${self.max_monthly_cost:.2f}"
            )

        return True, None

    def record_cost(self, actual_cost: float) -> None:
        """Record actual cost after job completion.

        Resets daily / monthly counters BEFORE accumulating so a job
        recorded just after midnight (UTC) goes into the new day's
        bucket, not yesterday's.
        """
        actual_cost = _validated_money(actual_cost, field_name="actual_cost")
        self.reset_if_needed()
        with self._lock:
            self.daily_spending += actual_cost
            self.monthly_spending += actual_cost

    def reset_if_needed(self) -> None:
        """Reset daily/monthly counters if needed."""
        now = datetime.now(UTC)
        with self._lock:
            # Reset daily
            if now.date() > self.last_reset.date():
                self.daily_spending = 0.0

            # Reset monthly
            if now.month != self.last_reset.month:
                self.monthly_spending = 0.0

            self.last_reset = now

    def get_spending_summary(self) -> dict[str, float]:
        """Get current spending summary."""
        self.reset_if_needed()

        with self._lock:
            return {
                "daily": self.daily_spending,
                "daily_limit": self.max_daily_cost,
                "daily_remaining": max(0, self.max_daily_cost - self.daily_spending),
                "monthly": self.monthly_spending,
                "monthly_limit": self.max_monthly_cost,
                "monthly_remaining": max(0, self.max_monthly_cost - self.monthly_spending),
            }


# Pre-defined safe test prompts (cheap to run)
CHEAP_TEST_PROMPTS = [
    {
        "prompt": "Write a 3-sentence summary of photosynthesis.",
        "expected_cost": 0.05,
        "description": "Ultra cheap - minimal output",
    },
    {
        "prompt": "List 5 benefits of exercise in bullet points.",
        "expected_cost": 0.05,
        "description": "Ultra cheap - structured output",
    },
    {
        "prompt": "Write a 2-line haiku about programming.",
        "expected_cost": 0.03,
        "description": "Minimal output test",
    },
    {
        "prompt": "What is 2+2? Answer in one word.",
        "expected_cost": 0.02,
        "description": "Absolute minimum test",
    },
    {
        "prompt": "Write a 10-line poem about the news.",
        "expected_cost": 0.10,
        "description": "Short creative task",
    },
    {
        "prompt": "Write a 1-paragraph essay on climate change (max 100 words).",
        "expected_cost": 0.15,
        "description": "Brief analytical task",
    },
]


def get_safe_test_prompt(index: int = 0) -> dict[str, Any]:
    """
    Get a pre-defined safe (cheap) test prompt.

    Args:
        index: Index of prompt to use (0-5)

    Returns:
        Dict with prompt, expected_cost, and description
    """
    if index < 0 or index >= len(CHEAP_TEST_PROMPTS):
        index = 0

    return CHEAP_TEST_PROMPTS[index]
