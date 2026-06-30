"""Published-benchmark quality priors for provisional routing.

Auto mode ranks models by measured quality per task type. A model without
eval data gets a *provisional* score; historically that score came from price
("higher price = assumed higher quality"), which under-ranks cheap-but-capable
models and pushes auto mode toward expensive picks even for simple queries.

These priors decouple the provisional quality estimate from price using public
benchmark standing, so auto mode routes sensibly out of the box WITHOUT anyone
running a paid eval. They are deliberately coarse, tiered estimates (not exact
scores), capped below measured eval results so real benchmarks always win once
they exist (see routing.auto_mode._estimate_quality), and they are refined or
overridden the moment `deepr eval` produces measured rankings.

Source (looked up June 2026, refresh on model changes):
- Artificial Analysis Intelligence Index: Claude Opus 4.8 ~61, GPT-5.5 ~60,
  Gemini 3.1 Pro ~57, Grok 4.3 ~53 - the four flagships are near-parity at the
  top (https://artificialanalysis.ai/models).
- Per-task standing: Opus 4.8 / GPT-5.5 lead coding; Gemini 3.1 Pro leads
  reasoning / data analysis / multimodal and "best cost-performance"; Grok is
  strong on agentic / tool-use and cheapest of the flagships; GPT-5.5 leads
  creative writing.
- Efficient tier punches above price: GPT-5 mini and Gemini Flash are
  near-frontier on easy tasks; Gemini Flash-Lite scores above GPT nano at half
  the cost. This is the price-as-quality failure these priors correct.

Tiers (0-1): frontier 0.78 (the cap), strong 0.75, capable-efficient 0.72,
budget 0.66. The point is the relative ordering being independent of price, not
the absolute number.
"""

from __future__ import annotations

_FRONTIER = 0.78
_STRONG = 0.75
_EFFICIENT = 0.72
_BUDGET = 0.66

# model_key ("provider/model") -> prior. Models not listed fall back to the
# price-tier heuristic in auto_mode._estimate_quality.
QUALITY_PRIORS: dict[str, float] = {
    # Frontier flagships + deep-research (near-parity at the top of the index).
    "openai/gpt-5.5": _FRONTIER,
    "openai/gpt-5.5-pro": _FRONTIER,
    "openai/gpt-5.4": _FRONTIER,
    "openai/gpt-5.4-pro": _FRONTIER,
    "openai/o3-deep-research": _FRONTIER,
    "openai/o4-mini-deep-research": _FRONTIER,
    "anthropic/claude-fable-5": _FRONTIER,
    "anthropic/claude-opus-4-8": _FRONTIER,
    "anthropic/claude-opus-4-7": _FRONTIER,
    "anthropic/claude-opus-4-6": _FRONTIER,
    "gemini/gemini-3.1-pro-preview": _FRONTIER,
    "gemini/gemini-3-pro-preview": _FRONTIER,
    "gemini/deep-research": _FRONTIER,
    "xai/grok-4-20-reasoning": _FRONTIER,
    "xai/grok-4-20-multi-agent": _FRONTIER,
    "azure-foundry/o3-deep-research": _FRONTIER,
    # Strong: just below the flagships.
    "openai/gpt-5.2": _STRONG,
    "openai/gpt-5": _STRONG,
    "openai/o3": _STRONG,
    "anthropic/claude-sonnet-5": _STRONG,
    "anthropic/claude-sonnet-4-6": _STRONG,
    "anthropic/claude-sonnet-4-5": _STRONG,
    "gemini/gemini-2.5-pro": _STRONG,
    "xai/grok-4-3": _STRONG,
    "xai/grok-4-20-non-reasoning": _STRONG,
    "azure-foundry/gpt-5": _STRONG,
    # Capable-efficient: near-frontier on easy tasks, far cheaper (the tier the
    # price proxy most under-ranked).
    "openai/gpt-5.4-mini": _EFFICIENT,
    "openai/gpt-5-mini": _EFFICIENT,
    "openai/o4-mini": _EFFICIENT,
    "openai/gpt-4.1": _EFFICIENT,
    "gemini/gemini-3.5-flash": _EFFICIENT,
    "gemini/gemini-3-flash-preview": _EFFICIENT,
    "azure-foundry/gpt-5-mini": _EFFICIENT,
    # Budget: solid on simple/factual lookups at the lowest cost.
    "openai/gpt-5.4-nano": _BUDGET,
    "openai/gpt-5-nano": _BUDGET,
    "openai/gpt-4.1-mini": _BUDGET,
    "openai/gpt-4.1-nano": _BUDGET,
    "gemini/gemini-3.1-flash-lite": _BUDGET,
    "gemini/gemini-3.1-flash-lite-preview": _BUDGET,
    "gemini/gemini-2.5-flash": _BUDGET,
    "gemini/gemini-2.5-flash-lite": _BUDGET,
}


def get_quality_prior(provider: str, model: str) -> float | None:
    """Published-benchmark quality prior for a model, or None to fall back."""
    return QUALITY_PRIORS.get(f"{provider}/{model}")
