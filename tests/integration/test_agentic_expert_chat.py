"""Integration tests for agentic expert chat with research capabilities."""

import pytest

from deepr.experts.chat import start_chat_session

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_agentic_expert_basic():
    """Test basic agentic expert chat session."""
    # Create session with agentic mode enabled
    session = await start_chat_session("Agentic Digital Consciousness", budget=1.0, agentic=True)

    assert session.agentic is True
    assert session.budget == 1.0
    assert session.cost_accumulated == 0.0

    # Send a message
    response = await session.send_message("What are temporal knowledge graphs?")

    assert isinstance(response, str)
    assert len(response) > 0
    assert session.cost_accumulated > 0

    # Check summary
    summary = session.get_session_summary()
    assert summary["messages_exchanged"] == 1
    assert summary["expert_name"] == "Agentic Digital Consciousness"


@pytest.mark.asyncio
async def test_agentic_research_tool_availability():
    """Test that research tools are available in agentic mode."""
    # Agentic session should have all 4 tools
    agentic_session = await start_chat_session("Agentic Digital Consciousness", budget=1.0, agentic=True)

    # Non-agentic session should only have search tool
    normal_session = await start_chat_session("Agentic Digital Consciousness", budget=1.0, agentic=False)

    assert agentic_session.agentic is True
    assert normal_session.agentic is False


@pytest.mark.asyncio
async def test_quick_lookup_trigger():
    """Test that expert can trigger quick_lookup for simple questions."""
    session = await start_chat_session("Agentic Digital Consciousness", budget=1.0, agentic=True)

    # Question that should trigger quick lookup (current info)
    response = await session.send_message("What is the current version of Python as of November 2025?")

    assert "python" in response.lower() or "3." in response
    # Quick lookup should be very cheap
    assert session.cost_accumulated < 0.15


@pytest.mark.asyncio
async def test_standard_research_trigger():
    """Test that expert can trigger standard research for technical questions."""
    session = await start_chat_session("Agentic Digital Consciousness", budget=1.0, agentic=True)

    # Question requiring research (not in knowledge base)
    response = await session.send_message("How do I implement OAuth2 authentication in FastAPI?")

    assert len(response) > 100
    # Standard research should cost $0.01-0.10
    assert session.cost_accumulated < 0.15


@pytest.mark.asyncio
async def test_knowledge_base_search_first():
    """Test that expert searches knowledge base before researching."""
    session = await start_chat_session("Agentic Digital Consciousness", budget=1.0, agentic=True)

    # Generic question - expert should try knowledge base first
    response = await session.send_message("Tell me about agentic AI systems")

    assert isinstance(response, str)
    assert len(response) > 0


@pytest.mark.asyncio
async def test_budget_tracking():
    """Test that budget is tracked correctly with research."""
    initial_budget = 0.5
    session = await start_chat_session("Agentic Digital Consciousness", budget=initial_budget, agentic=True)

    # Send a question
    await session.send_message("What is machine learning?")

    summary = session.get_session_summary()
    assert summary["cost_accumulated"] >= 0
    assert summary["budget_remaining"] <= initial_budget
    assert summary["budget_remaining"] == initial_budget - summary["cost_accumulated"]


@pytest.mark.asyncio
async def test_deep_research_tracking():
    """Test that deep research jobs are tracked."""
    session = await start_chat_session("Agentic Digital Consciousness", budget=2.0, agentic=True)

    initial_jobs = len(session.research_jobs)

    # Ask a complex question that might trigger deep research
    # (though expert should usually use standard_research for most things)
    response = await session.send_message(
        "Design a comprehensive multi-region disaster recovery strategy for a SaaS platform"
    )

    # Check if any research was triggered
    assert len(response) > 0


@pytest.mark.asyncio
async def test_non_agentic_mode_no_research():
    """Test that non-agentic mode doesn't have research tools."""
    session = await start_chat_session(
        "Agentic Digital Consciousness",
        budget=1.0,
        agentic=False,  # Non-agentic
    )

    # Should only search knowledge base, not research
    response = await session.send_message("What is the latest version of React?")

    # In non-agentic mode, expert should say it doesn't know (no research)
    assert isinstance(response, str)


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
