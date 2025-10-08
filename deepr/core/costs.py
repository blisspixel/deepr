"""Cost estimation, tracking, and control for research operations."""

from typing import Optional, Dict, Literal
from dataclasses import dataclass
from datetime import datetime, timezone


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

    # Pricing per 1M tokens (as of Jan 2025)
    PRICING = {
        "o3-deep-research": {
            "input": 2.00,   # $2.00 per 1M input tokens
            "output": 8.00,  # $8.00 per 1M output tokens
        },
        "o4-mini-deep-research": {
            "input": 1.10,   # $1.10 per 1M input tokens
            "output": 4.40,  # $4.40 per 1M output tokens
        },
        "gpt-5": {
            "input": 0.05,   # GPT-5 reasoning model
            "output": 0.15,
        },
        "gpt-5-mini": {
            "input": 0.01,   # GPT-5-mini (fast reasoning)
            "output": 0.03,
        },
    }

    @classmethod
    def estimate_prompt_tokens(cls, prompt: str, documents: Optional[list] = None) -> int:
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
        documents: Optional[list] = None,
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
        # Get base model pricing
        pricing = cls.PRICING.get(model, cls.PRICING["o3-deep-research"])

        # Estimate input tokens
        input_tokens = cls.estimate_prompt_tokens(prompt, documents)

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

        return CostEstimate(
            min_cost=round(min_cost, 2),
            max_cost=round(max_cost, 2),
            expected_cost=round(expected_cost, 2),
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
        pricing = cls.PRICING.get(model, cls.PRICING["o3-deep-research"])

        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]

        # Reasoning tokens typically billed at output rate
        reasoning_cost = (reasoning_tokens / 1_000_000) * pricing["output"]

        return round(input_cost + output_cost + reasoning_cost, 4)


class CostController:
    """
    Control and limit research costs.

    Prevents accidental overspending.
    """

    def __init__(
        self,
        max_cost_per_job: float = 10.0,
        max_daily_cost: float = 100.0,
        max_monthly_cost: float = 1000.0,
    ):
        """
        Initialize cost controller with limits.

        Args:
            max_cost_per_job: Maximum cost allowed for single job
            max_daily_cost: Maximum daily spending
            max_monthly_cost: Maximum monthly spending
        """
        self.max_cost_per_job = max_cost_per_job
        self.max_daily_cost = max_daily_cost
        self.max_monthly_cost = max_monthly_cost

        self.daily_spending = 0.0
        self.monthly_spending = 0.0
        self.last_reset = datetime.now(timezone.utc)

    def check_cost_limit(self, estimate: CostEstimate) -> tuple[bool, Optional[str]]:
        """
        Check if operation would exceed cost limits.

        Args:
            estimate: Cost estimate for operation

        Returns:
            (allowed, reason) - reason is None if allowed
        """
        # Check per-job limit
        if estimate.max_cost > self.max_cost_per_job:
            return False, (
                f"Job may cost ${estimate.max_cost:.2f}, exceeds limit of "
                f"${self.max_cost_per_job:.2f}. Use --cost-sensitive or reduce scope."
            )

        # Check daily limit
        if self.daily_spending + estimate.expected_cost > self.max_daily_cost:
            return False, (
                f"Daily spending (${self.daily_spending:.2f}) + estimated cost "
                f"(${estimate.expected_cost:.2f}) exceeds daily limit of "
                f"${self.max_daily_cost:.2f}"
            )

        # Check monthly limit
        if self.monthly_spending + estimate.expected_cost > self.max_monthly_cost:
            return False, (
                f"Monthly spending (${self.monthly_spending:.2f}) + estimated cost "
                f"(${estimate.expected_cost:.2f}) exceeds monthly limit of "
                f"${self.max_monthly_cost:.2f}"
            )

        return True, None

    def record_cost(self, actual_cost: float):
        """Record actual cost after job completion."""
        self.daily_spending += actual_cost
        self.monthly_spending += actual_cost

    def reset_if_needed(self):
        """Reset daily/monthly counters if needed."""
        now = datetime.now(timezone.utc)

        # Reset daily
        if now.date() > self.last_reset.date():
            self.daily_spending = 0.0

        # Reset monthly
        if now.month != self.last_reset.month:
            self.monthly_spending = 0.0

        self.last_reset = now

    def get_spending_summary(self) -> Dict[str, float]:
        """Get current spending summary."""
        self.reset_if_needed()

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


def get_safe_test_prompt(index: int = 0) -> Dict:
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
