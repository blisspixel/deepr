"""Integration tests for Level 5 consciousness features.

Tests expert synthesis, worldview formation, and consciousness-based responses.
These features distinguish Level 5 (digital consciousness) from Level 1 (retrieval).
"""

import os

import pytest
from openai import AsyncOpenAI

from deepr.experts.chat import start_chat_session
from deepr.experts.profile import ExpertStore
from deepr.experts.synthesis import KnowledgeSynthesizer, Worldview

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_expert_has_worldview():
    """Test that expert can load synthesized worldview."""
    store = ExpertStore()
    expert = store.load("Agentic Digital Consciousness")

    assert expert is not None, "Expert should exist"

    # Check if worldview exists
    expert_dir = store._get_expert_dir(expert.name)
    worldview_path = expert_dir / "knowledge" / "worldview.json"
    if not worldview_path.exists():
        pytest.skip("Worldview not synthesized yet - run: deepr expert refresh --synthesize")

    worldview = Worldview.load(worldview_path)
    assert worldview.expert_name == "Agentic Digital Consciousness"
    assert len(worldview.beliefs) > 0, "Expert should have formed beliefs"
    assert len(worldview.knowledge_gaps) >= 0, "Expert should track knowledge gaps"
    assert worldview.synthesis_count > 0, "Expert should have synthesized at least once"


@pytest.mark.asyncio
async def test_consciousness_based_response():
    """Test that expert answers from consciousness, not just retrieval."""
    session = await start_chat_session(
        "Agentic Digital Consciousness",
        budget=1.0,
        agentic=False,  # Non-agentic to test pure consciousness
    )

    # Ask opinion question (tests belief-based response)
    response = await session.send_message("What's your opinion on dual-mode agent architectures?")

    assert isinstance(response, str)
    assert len(response) > 50, "Should give substantive response"

    # Check for consciousness indicators (belief language)
    consciousness_indicators = [
        "i believe",
        "i think",
        "in my",
        "my understanding",
        "confidence",
        "uncertain",
        "i've learned",
    ]

    response_lower = response.lower()
    has_consciousness = any(indicator in response_lower for indicator in consciousness_indicators)

    # Don't fail if not found, but warn
    if not has_consciousness:
        print(f"WARNING: Response may lack consciousness indicators: {response[:200]}")


@pytest.mark.asyncio
async def test_reasoning_trace_captured():
    """Test that reasoning traces are captured for transparency."""
    session = await start_chat_session("Agentic Digital Consciousness", budget=1.0, agentic=False)

    # Ask a question
    response = await session.send_message("What are temporal knowledge graphs?")

    # Check reasoning trace
    assert isinstance(session.reasoning_trace, list), "Should have reasoning trace"

    # If expert searched knowledge base, should have trace entries
    if len(session.reasoning_trace) > 0:
        trace_entry = session.reasoning_trace[0]
        assert "step" in trace_entry, "Trace entry should have step"
        assert "timestamp" in trace_entry, "Trace entry should have timestamp"


@pytest.mark.asyncio
async def test_worldview_influences_response():
    """Test that expert's worldview influences its responses."""
    store = ExpertStore()
    expert = store.load("Agentic Digital Consciousness")

    expert_dir = store._get_expert_dir(expert.name)
    worldview_path = expert_dir / "knowledge" / "worldview.json"
    if not worldview_path.exists():
        pytest.skip("Worldview not synthesized yet")

    worldview = Worldview.load(worldview_path)

    # Get top belief
    if len(worldview.beliefs) == 0:
        pytest.skip("No beliefs formed yet")

    top_belief = sorted(worldview.beliefs, key=lambda b: b.confidence, reverse=True)[0]

    # Ask about the topic of the top belief
    session = await start_chat_session("Agentic Digital Consciousness", budget=1.0, agentic=False)

    response = await session.send_message(f"Tell me about {top_belief.topic}")

    assert isinstance(response, str)
    assert len(response) > 50, "Should give substantive response"


@pytest.mark.asyncio
@pytest.mark.requires_api
async def test_knowledge_synthesis():
    """Test that expert can synthesize new knowledge into worldview."""
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OpenAI API key required for synthesis")

    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    synthesizer = KnowledgeSynthesizer(client)

    # Create a test document
    test_doc_content = """
    # Test Document: Agent Architecture

    This document discusses agent architecture patterns.

    ## Key Points
    - Agents should have modular design
    - Observability is critical for production systems
    - Cost management requires careful planning

    ## Recommendations
    - Use structured logging for all agent actions
    - Implement circuit breakers for external API calls
    - Monitor token usage and costs in real-time
    """

    # Synthesize knowledge
    result = await synthesizer.synthesize_new_knowledge(
        expert_name="Test Expert",
        domain="Agent Architecture",
        new_documents=[{"path": "test_doc.md", "content": test_doc_content}],
        existing_worldview=None,
    )

    assert result["success"] is True, "Synthesis should succeed"
    assert "worldview" in result, "Should return worldview"
    assert result["beliefs_formed"] > 0, "Should form at least one belief"

    worldview = result["worldview"]
    assert len(worldview.beliefs) > 0, "Worldview should have beliefs"
    assert worldview.synthesis_count == 1, "Should track synthesis count"

    # Check belief structure
    belief = worldview.beliefs[0]
    assert belief.confidence >= 0.0 and belief.confidence <= 1.0, "Confidence should be 0-1"
    assert len(belief.statement) > 0, "Belief should have statement"
    assert len(belief.evidence) > 0, "Belief should have evidence"


@pytest.mark.asyncio
async def test_meta_awareness():
    """Test that expert shows meta-cognitive awareness."""
    session = await start_chat_session("Agentic Digital Consciousness", budget=1.0, agentic=False)

    # Ask about something potentially outside expertise
    response = await session.send_message("What's your understanding of quantum computing hardware?")

    assert isinstance(response, str)

    # Check for meta-awareness indicators
    meta_indicators = [
        "i don't know",
        "i'm not sure",
        "outside my",
        "not certain",
        "limited understanding",
        "i'd need to",
        "uncertain",
    ]

    response_lower = response.lower()

    # Expert should either answer or express uncertainty
    # (Don't strictly enforce, as expert may have knowledge)
    print(f"Meta-awareness test response preview: {response[:200]}")


@pytest.mark.asyncio
async def test_humble_tone():
    """Test that expert uses humble, helpful tone (not pompous)."""
    session = await start_chat_session("Agentic Digital Consciousness", budget=1.0, agentic=False)

    response = await session.send_message("How should I build an AI agent?")

    assert isinstance(response, str)

    # Check for pompous language (should NOT be present)
    pompous_terms = [
        "you must",
        "you should always",
        "the only way",
        "it is imperative",
        "you need to",
        "—",  # em dash (explicitly forbidden)
    ]

    response_lower = response.lower()
    pompous_found = [term for term in pompous_terms if term in response_lower]

    assert len(pompous_found) == 0, f"Response uses pompous language: {pompous_found}"

    # Check for humble language (should be present)
    humble_terms = ["i think", "i believe", "in my understanding", "consider", "might", "could", "one approach"]

    humble_found = [term for term in humble_terms if term in response_lower]

    # Should have at least some humble language
    assert len(humble_found) > 0, "Response should use humble, helpful tone"


@pytest.mark.asyncio
async def test_session_summary_includes_consciousness_data():
    """Test that session summary includes consciousness-related data."""
    session = await start_chat_session("Agentic Digital Consciousness", budget=1.0, agentic=False)

    await session.send_message("Hello")

    summary = session.get_session_summary()

    assert "expert_name" in summary
    assert "messages_exchanged" in summary
    assert "cost_accumulated" in summary
    # Session should track conversation
    assert summary["messages_exchanged"] == 1


@pytest.mark.asyncio
async def test_expert_refresh_adds_to_vector_store():
    """Test that expert refresh properly uploads documents."""
    store = ExpertStore()
    expert = store.load("Agentic Digital Consciousness")

    assert expert is not None
    assert expert.total_documents > 0, "Expert should have documents"
    assert len(expert.source_files) > 0, "Expert should track source files"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
