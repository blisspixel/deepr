"""Property tests for ExpertSkillWrapper.

Feature: mcp-client-agent-interop
Properties: 5, 24, 25, 28, 33, 34
Validates: Requirements 1.6, 1.7, 12.1, 12.2, 12.5, 16.3, 16.4
"""

from __future__ import annotations

import asyncio

from hypothesis import given, settings
from hypothesis import strategies as st

from deepr.mcp.client.errors import MCPErrorCode, StructuredError
from deepr.mcp.client.profile import MCPClientProfile
from deepr.experts.skills.expert_skill import (
    ExpertSkillWrapper,
    KnowledgeGap,
    ResearchContext,
    ToolInfo,
    ToolSuggestion,
)


# --- Strategies ---

tool_names_st = st.sampled_from([
    "domain_lookup", "batch_lookup", "dns_check",
    "paper_search", "citation_lookup",
    "company_analysis", "market_data",
])

domain_st = st.from_regex(r"[a-z]{3,10}\.(com|org|net|io)", fullmatch=True)

profile_st = st.builds(
    MCPClientProfile,
    name=st.just("test-server"),
    command=st.just("test"),
    auto_approve=st.lists(tool_names_st, max_size=3, unique=True),
    require_approval=st.lists(tool_names_st, max_size=3, unique=True),
)


# --- Property 5: Approval decision matches profile configuration ---

@settings(max_examples=100)
@given(
    tool_name=tool_names_st,
    auto_approve=st.lists(tool_names_st, max_size=4, unique=True),
    require_approval=st.lists(tool_names_st, max_size=4, unique=True),
)
def test_approval_decision_matches_profile(
    tool_name: str,
    auto_approve: list[str],
    require_approval: list[str],
) -> None:
    """Property 5: Approval decision matches profile configuration.

    **Validates: Requirements 1.6, 1.7**
    """
    profile = MCPClientProfile(
        name="test",
        command="test",
        auto_approve=auto_approve,
        require_approval=require_approval,
    )
    wrapper = ExpertSkillWrapper(profile)

    needs_approval = wrapper._needs_approval(tool_name)

    if tool_name in auto_approve:
        assert needs_approval is False, "auto_approve tools should not need approval"
    elif tool_name in require_approval:
        assert needs_approval is True, "require_approval tools should need approval"
    else:
        # Default: require approval
        assert needs_approval is True, "unlisted tools should default to requiring approval"


# --- Property 24: Domain trigger detection ---

@settings(max_examples=100)
@given(domain=domain_st)
def test_domain_trigger_detection(domain: str) -> None:
    """Property 24: Domain trigger detection.

    For any research context containing a valid company domain and where
    domain_lookup is available, should_trigger includes a domain_lookup suggestion.

    **Validates: Requirements 12.1**
    """
    profile = MCPClientProfile(
        name="recon",
        command="recon",
        auto_approve=["domain_lookup"],
    )
    wrapper = ExpertSkillWrapper(profile)

    context = ResearchContext(text=f"Researching {domain} for analysis")
    tools = [ToolInfo(server_name="recon", tool_name="domain_lookup")]

    suggestions = wrapper.should_trigger(context, tools)

    domain_suggestions = [s for s in suggestions if s.tool_name == "domain_lookup"]
    assert len(domain_suggestions) >= 1, f"Expected domain_lookup suggestion for {domain}"
    assert any(
        domain in s.arguments.get("domain", "") for s in domain_suggestions
    ), f"Expected domain {domain} in suggestion arguments"


# --- Property 25: Knowledge gap triggers matching tools ---

@settings(max_examples=100)
@given(
    category=st.sampled_from(["infrastructure", "academic", "strategic"]),
)
def test_knowledge_gap_triggers_matching_tools(category: str) -> None:
    """Property 25: Knowledge gap triggers matching tools.

    For any knowledge gap with a category matching available tools,
    should_trigger includes suggestions for those tools.

    **Validates: Requirements 12.2**
    """
    from deepr.experts.skills.expert_skill import _GAP_TOOL_MAP

    profile = MCPClientProfile(
        name="test",
        command="test",
        auto_approve=_GAP_TOOL_MAP.get(category, []),
    )
    wrapper = ExpertSkillWrapper(profile)

    gap = KnowledgeGap(category=category, description="Need more data")
    context = ResearchContext(knowledge_gaps=[gap])

    # Make all matching tools available
    expected_tools = _GAP_TOOL_MAP.get(category, [])
    tools = [ToolInfo(server_name="test", tool_name=t) for t in expected_tools]

    suggestions = wrapper.should_trigger(context, tools)

    suggested_names = {s.tool_name for s in suggestions}
    for tool_name in expected_tools:
        assert tool_name in suggested_names, (
            f"Expected {tool_name} suggestion for {category} gap"
        )


# --- Property 28: Graceful degradation for missing tools ---

@settings(max_examples=100)
@given(
    category=st.sampled_from(["infrastructure", "academic", "strategic"]),
)
def test_graceful_degradation_missing_tools(category: str) -> None:
    """Property 28: Graceful degradation for missing tools.

    When referenced tools are not available, should_trigger does not
    raise and simply omits those tools from suggestions.

    **Validates: Requirements 12.5**
    """
    profile = MCPClientProfile(name="test", command="test")
    wrapper = ExpertSkillWrapper(profile)

    gap = KnowledgeGap(category=category, description="Need data")
    context = ResearchContext(
        text="example.com analysis",
        knowledge_gaps=[gap],
    )

    # No tools available
    suggestions = wrapper.should_trigger(context, [])
    # Should not raise, and should return empty or only non-matching
    assert isinstance(suggestions, list)


# --- Property 33: Retryable errors trigger exactly one retry ---

@settings(max_examples=100)
@given(
    error_code=st.sampled_from([
        MCPErrorCode.TIMEOUT,
        MCPErrorCode.CONNECTION_LOST,
        MCPErrorCode.SERVER_ERROR,
    ]),
)
def test_retryable_errors_trigger_one_retry(error_code: MCPErrorCode) -> None:
    """Property 33: Retryable errors trigger exactly one retry.

    For any retryable error, execute attempts exactly one retry.

    **Validates: Requirements 16.3**
    """
    profile = MCPClientProfile(name="test", command="test")
    wrapper = ExpertSkillWrapper(profile)

    call_count = 0

    async def mock_call(server: str, tool: str, args: dict) -> StructuredError:
        nonlocal call_count
        call_count += 1
        return StructuredError(
            code=error_code,
            message="Test error",
            retryable=True,
        )

    suggestion = ToolSuggestion(
        server_name="test",
        tool_name="domain_lookup",
        arguments={"domain": "test.com"},
    )

    asyncio.get_event_loop().run_until_complete(
        wrapper.execute(suggestion, mock_call)
    )

    assert call_count == 2, f"Expected 2 attempts (initial + 1 retry), got {call_count}"


# --- Property 34: Exhausted retries create knowledge gaps ---

@settings(max_examples=100)
@given(
    error_code=st.sampled_from([
        MCPErrorCode.TIMEOUT,
        MCPErrorCode.CONNECTION_LOST,
        MCPErrorCode.SERVER_ERROR,
    ]),
)
def test_exhausted_retries_return_error(error_code: MCPErrorCode) -> None:
    """Property 34: Exhausted retries create knowledge gaps.

    When all retries are exhausted, a StructuredError is returned
    (not an unhandled exception).

    **Validates: Requirements 16.4**
    """
    profile = MCPClientProfile(name="test", command="test")
    wrapper = ExpertSkillWrapper(profile)

    async def mock_call(server: str, tool: str, args: dict) -> StructuredError:
        return StructuredError(
            code=error_code,
            message="Persistent failure",
            retryable=True,
        )

    suggestion = ToolSuggestion(
        server_name="test",
        tool_name="lookup",
        arguments={},
    )

    result = asyncio.get_event_loop().run_until_complete(
        wrapper.execute(suggestion, mock_call)
    )

    assert isinstance(result, StructuredError), "Exhausted retries should return StructuredError"
    assert result.code == error_code
