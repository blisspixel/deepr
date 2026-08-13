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

Source (reviewed August 2026, refresh on model changes):
- xAI's Grok 4.6 release reports Grok 4.6 and GPT-5.6 Sol at 61 on the
  Artificial Analysis Intelligence Index, with Fable 5 at 62
  (https://x.ai/news/grok-4-6).
- Anthropic describes Opus 5 as a step-change improvement over Opus 4.8 for
  deep reasoning and long-horizon agentic work
  (https://platform.claude.com/docs/en/about-claude/models/whats-new-opus-5).
- Current provider reports place the newest flagships in the same broad tier,
  but those reports are not interchangeable held-out evaluations. Deepr keeps
  the priors coarse until its own provider-free or explicitly budgeted evals
  produce measured rankings.
- Efficient tier punches above price: GPT-5 mini and Gemini Flash are
  near-frontier on easy tasks; Gemini Flash-Lite scores above GPT nano at half
  the cost. This is the price-as-quality failure these priors correct.
- Google's July 21, 2026 Gemini 3.6 Flash and Gemini 3.5 Flash-Lite launch
  reports the former near larger frontier models and the latter as its
  high-volume efficiency model
  (https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-6-flash-3-5-flash-lite-3-5-flash-cyber/).

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
    "openai/gpt-5.6-sol": _FRONTIER,
    "openai/gpt-5.5": _FRONTIER,
    "openai/gpt-5.5-pro": _FRONTIER,
    "openai/gpt-5.4": _FRONTIER,
    "openai/gpt-5.4-pro": _FRONTIER,
    "openai/o3-deep-research": _FRONTIER,
    "openai/o4-mini-deep-research": _FRONTIER,
    "anthropic/claude-fable-5": _FRONTIER,
    "anthropic/claude-opus-5": _FRONTIER,
    "anthropic/claude-opus-4-8": _FRONTIER,
    "anthropic/claude-opus-4-7": _FRONTIER,
    "anthropic/claude-opus-4-6": _FRONTIER,
    "gemini/gemini-3.1-pro-preview": _FRONTIER,
    "gemini/deep-research": _FRONTIER,
    "xai/grok-4-20-reasoning": _FRONTIER,
    "xai/grok-4-20-multi-agent": _FRONTIER,
    "xai/grok-4-6": _FRONTIER,
    "azure-foundry/o3-deep-research": _FRONTIER,
    # Strong: just below the flagships.
    "openai/gpt-5.2": _STRONG,
    "openai/gpt-5": _STRONG,
    "openai/gpt-5.6-terra": _STRONG,
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
    "gemini/gemini-3.6-flash": _EFFICIENT,
    "gemini/gemini-3.5-flash": _EFFICIENT,
    "gemini/gemini-3-flash-preview": _EFFICIENT,
    "azure-foundry/gpt-5-mini": _EFFICIENT,
    # Budget: solid on simple/factual lookups at the lowest cost.
    "openai/gpt-5.4-nano": _BUDGET,
    "openai/gpt-5.6-luna": _BUDGET,
    "openai/gpt-5-nano": _BUDGET,
    "openai/gpt-4.1-mini": _BUDGET,
    "openai/gpt-4.1-nano": _BUDGET,
    "gemini/gemini-3.5-flash-lite": _BUDGET,
    "gemini/gemini-3.1-flash-lite": _BUDGET,
    "gemini/gemini-2.5-flash": _BUDGET,
    "gemini/gemini-2.5-flash-lite": _BUDGET,
}


def get_quality_prior(provider: str, model: str) -> float | None:
    """Published-benchmark quality prior for a model, or None to fall back."""
    return QUALITY_PRIORS.get(f"{provider}/{model}")
