"""Research CLI cost-estimation prompt contracts."""

from deepr.cli.commands.research import _build_research_prompt
from deepr.core.costs import CostEstimator


def test_context_is_included_in_the_exact_prompt_reserved_for_submission() -> None:
    context = "evidence " * 100_000
    expanded = _build_research_prompt("What changed?", context)

    short_estimate = CostEstimator.estimate_cost("What changed?", "o3-deep-research")
    expanded_estimate = CostEstimator.estimate_cost(expanded, "o3-deep-research")

    assert context in expanded
    assert expanded_estimate.max_cost > short_estimate.max_cost
