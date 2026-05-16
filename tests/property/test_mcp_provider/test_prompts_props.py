"""Property tests for MCP provider prompts.

Feature: mcp-client-agent-interop
Property: 22
Validates: Requirements 10.4
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from deepr.mcp.provider.prompts import PromptRenderer

# --- Strategies ---

safe_text_st = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"),
        blacklist_characters="{}",
    ),
    min_size=1,
    max_size=30,
)


# --- Property 22: Prompt template rendering ---


@settings(max_examples=100)
@given(
    topic=safe_text_st,
    budget=safe_text_st,
    expert=safe_text_st,
    depth=safe_text_st,
)
def test_research_workflow_rendering(
    topic: str,
    budget: str,
    expert: str,
    depth: str,
) -> None:
    """Property 22: Prompt template rendering (research-workflow).

    For any set of argument values, the rendered output contains all
    provided values with no unresolved placeholders for provided arguments.

    **Validates: Requirements 10.4**
    """
    renderer = PromptRenderer()
    result = renderer.render(
        "research-workflow",
        {
            "topic": topic,
            "budget": budget,
            "expert": expert,
            "depth": depth,
        },
    )

    # All values should appear in output
    assert topic in result, f"Topic '{topic}' not in rendered output"
    assert budget in result, f"Budget '{budget}' not in rendered output"
    assert expert in result, f"Expert '{expert}' not in rendered output"
    assert depth in result, f"Depth '{depth}' not in rendered output"

    # No unresolved placeholders for provided args
    assert "{{topic}}" not in result
    assert "{{budget}}" not in result
    assert "{{expert}}" not in result
    assert "{{depth}}" not in result


@settings(max_examples=100)
@given(
    expert=safe_text_st,
    question=safe_text_st,
    context=safe_text_st,
)
def test_expert_consult_rendering(
    expert: str,
    question: str,
    context: str,
) -> None:
    """Property 22: Prompt template rendering (expert-consult).

    **Validates: Requirements 10.4**
    """
    renderer = PromptRenderer()
    result = renderer.render(
        "expert-consult",
        {
            "expert": expert,
            "question": question,
            "context": context,
        },
    )

    assert expert in result
    assert question in result
    assert context in result
    assert "{{expert}}" not in result
    assert "{{question}}" not in result
    assert "{{context}}" not in result


@settings(max_examples=100)
@given(
    sector=safe_text_st,
    companies=safe_text_st,
    timeframe=safe_text_st,
)
def test_sector_analysis_rendering(
    sector: str,
    companies: str,
    timeframe: str,
) -> None:
    """Property 22: Prompt template rendering (sector-analysis).

    **Validates: Requirements 10.4**
    """
    renderer = PromptRenderer()
    result = renderer.render(
        "sector-analysis",
        {
            "sector": sector,
            "companies": companies,
            "timeframe": timeframe,
        },
    )

    assert sector in result
    assert companies in result
    assert timeframe in result
    assert "{{sector}}" not in result
    assert "{{companies}}" not in result
    assert "{{timeframe}}" not in result
