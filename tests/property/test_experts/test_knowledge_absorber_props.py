"""Property tests for KnowledgeAbsorber.

Feature: mcp-client-agent-interop
Properties: 27, 31
Validates: Requirements 12.4, 15.3
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from deepr.experts.skills.knowledge_absorber import (
    AbsorbedFinding,
    KnowledgeAbsorber,
)

# --- Strategies ---

source_type_st = st.sampled_from(["DNS", "dns", "whois", "paper", "citation", "scrape", "api", "market"])

category_st = st.sampled_from(["infrastructure", "academic", "strategic"])

finding_item_st = st.fixed_dictionaries(
    {
        "text": st.text(min_size=1, max_size=50),
        "value": st.text(min_size=1, max_size=50),
    }
)

tool_response_st = st.fixed_dictionaries(
    {
        "results": st.lists(finding_item_st, min_size=1, max_size=5),
    }
)


# --- Property 27: Knowledge absorption categorization and confidence ---


@settings(max_examples=100)
@given(
    source_type=source_type_st,
    response=tool_response_st,
)
def test_absorption_categorization_and_confidence(
    source_type: str,
    response: dict,
) -> None:
    """Property 27: Knowledge absorption categorization and confidence.

    For any structured tool response with known source type, the absorber
    produces findings where:
    - category is one of (infrastructure, academic, strategic)
    - confidence is in [0.0, 1.0]
    - source_type matches the tool's declared type

    **Validates: Requirements 12.4, 15.3**
    """
    absorber = KnowledgeAbsorber()
    findings = absorber.absorb(response, source_type=source_type, source_tool="test/tool")

    assert len(findings) > 0, "Should produce at least one finding"

    valid_categories = {"infrastructure", "academic", "strategic"}
    for finding in findings:
        assert isinstance(finding, AbsorbedFinding)
        assert finding.category in valid_categories, f"Invalid category: {finding.category}"
        assert 0.0 <= finding.confidence <= 1.0, f"Confidence out of range: {finding.confidence}"
        assert finding.source_type == source_type, f"Source type mismatch: {finding.source_type} != {source_type}"


# --- Property 31: Recon absorption produces high-confidence DNS beliefs ---


@settings(max_examples=100)
@given(
    provider=st.text(min_size=1, max_size=20),
    services=st.lists(
        st.fixed_dictionaries({"text": st.text(min_size=1, max_size=30)}),
        min_size=1,
        max_size=5,
    ),
    related_domains=st.lists(
        st.fixed_dictionaries({"text": st.text(min_size=1, max_size=30)}),
        min_size=0,
        max_size=3,
    ),
    insights=st.lists(
        st.fixed_dictionaries({"text": st.text(min_size=1, max_size=50)}),
        min_size=0,
        max_size=3,
    ),
)
def test_recon_absorption_high_confidence_dns(
    provider: str,
    services: list[dict],
    related_domains: list[dict],
    insights: list[dict],
) -> None:
    """Property 31: Recon absorption produces high-confidence DNS beliefs.

    For any valid recon JSON response (containing provider, services,
    related_domains, insights), the absorber produces beliefs with
    confidence >= 0.8 and source_type = "DNS".

    **Validates: Requirements 15.3**
    """
    recon_response = {
        "provider": provider,
        "services": services,
        "related_domains": related_domains,
        "insights": insights,
    }

    absorber = KnowledgeAbsorber()
    findings = absorber.absorb(
        recon_response,
        source_type="DNS",
        source_tool="recon/domain_lookup",
    )

    assert len(findings) > 0, "Should produce findings from recon response"

    for finding in findings:
        assert finding.confidence >= 0.8, f"DNS findings should have confidence >= 0.8, got {finding.confidence}"
        assert finding.source_type == "DNS"
        assert finding.category == "infrastructure"
