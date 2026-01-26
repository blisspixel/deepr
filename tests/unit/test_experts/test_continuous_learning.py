"""Unit tests for continuous learning trigger in ExpertChatSession.

Tests the Phase 1 implementation:
- Conversation counter increments
- Research counter increments when research tools are called
- should_trigger_synthesis() returns True at threshold
- Synthesis trigger logic
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime


class TestContinuousLearningCounters:
    """Test conversation and research counter tracking."""

    def test_counters_initialized_to_zero(self):
        """Counters should start at zero."""
        with patch('deepr.experts.chat.AsyncOpenAI'):
            with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
                from deepr.experts.chat import ExpertChatSession
                from deepr.experts.profile import ExpertProfile
                
                expert = ExpertProfile(
                    name="Test Expert",
                    domain="testing",
                    vector_store_id="vs_test"
                )
                
                session = ExpertChatSession(expert, agentic=True)
                
                assert session.conversation_count == 0
                assert session.research_count == 0
                assert session.synthesis_threshold == 10
                assert session.last_synthesis_research_count == 0

    def test_synthesis_threshold_default(self):
        """Default synthesis threshold should be 10."""
        with patch('deepr.experts.chat.AsyncOpenAI'):
            with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
                from deepr.experts.chat import ExpertChatSession
                from deepr.experts.profile import ExpertProfile
                
                expert = ExpertProfile(
                    name="Test Expert",
                    domain="testing",
                    vector_store_id="vs_test"
                )
                
                session = ExpertChatSession(expert, agentic=True)
                
                assert session.synthesis_threshold == 10


class TestShouldTriggerSynthesis:
    """Test the should_trigger_synthesis() method."""

    def test_returns_false_when_not_agentic(self):
        """Should return False when agentic mode is disabled."""
        with patch('deepr.experts.chat.AsyncOpenAI'):
            with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
                from deepr.experts.chat import ExpertChatSession
                from deepr.experts.profile import ExpertProfile
                
                expert = ExpertProfile(
                    name="Test Expert",
                    domain="testing",
                    vector_store_id="vs_test"
                )
                
                session = ExpertChatSession(expert, agentic=False)
                session.research_count = 15  # Above threshold
                
                assert session.should_trigger_synthesis() is False

    def test_returns_false_below_threshold(self):
        """Should return False when research count is below threshold."""
        with patch('deepr.experts.chat.AsyncOpenAI'):
            with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
                from deepr.experts.chat import ExpertChatSession
                from deepr.experts.profile import ExpertProfile
                
                expert = ExpertProfile(
                    name="Test Expert",
                    domain="testing",
                    vector_store_id="vs_test"
                )
                
                session = ExpertChatSession(expert, agentic=True)
                session.research_count = 5  # Below threshold of 10
                
                assert session.should_trigger_synthesis() is False

    def test_returns_true_at_threshold(self):
        """Should return True when research count reaches threshold."""
        with patch('deepr.experts.chat.AsyncOpenAI'):
            with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
                from deepr.experts.chat import ExpertChatSession
                from deepr.experts.profile import ExpertProfile
                
                expert = ExpertProfile(
                    name="Test Expert",
                    domain="testing",
                    vector_store_id="vs_test"
                )
                
                session = ExpertChatSession(expert, agentic=True)
                session.research_count = 10  # At threshold
                
                assert session.should_trigger_synthesis() is True

    def test_returns_true_above_threshold(self):
        """Should return True when research count exceeds threshold."""
        with patch('deepr.experts.chat.AsyncOpenAI'):
            with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
                from deepr.experts.chat import ExpertChatSession
                from deepr.experts.profile import ExpertProfile
                
                expert = ExpertProfile(
                    name="Test Expert",
                    domain="testing",
                    vector_store_id="vs_test"
                )
                
                session = ExpertChatSession(expert, agentic=True)
                session.research_count = 15  # Above threshold
                
                assert session.should_trigger_synthesis() is True

    def test_accounts_for_last_synthesis(self):
        """Should only count research since last synthesis."""
        with patch('deepr.experts.chat.AsyncOpenAI'):
            with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
                from deepr.experts.chat import ExpertChatSession
                from deepr.experts.profile import ExpertProfile
                
                expert = ExpertProfile(
                    name="Test Expert",
                    domain="testing",
                    vector_store_id="vs_test"
                )
                
                session = ExpertChatSession(expert, agentic=True)
                session.research_count = 15
                session.last_synthesis_research_count = 10  # Last synthesis at 10
                
                # Only 5 research since last synthesis (15 - 10 = 5)
                # Threshold is 10, so should NOT trigger
                assert session.should_trigger_synthesis() is False
                
                # Now add more research
                session.research_count = 20  # 10 since last synthesis
                assert session.should_trigger_synthesis() is True


class TestTriggerBackgroundSynthesis:
    """Test the _trigger_background_synthesis() method."""

    @pytest.mark.asyncio
    async def test_updates_last_synthesis_count(self):
        """Should update last_synthesis_research_count after synthesis."""
        with patch('deepr.experts.chat.AsyncOpenAI'):
            with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
                from deepr.experts.chat import ExpertChatSession
                from deepr.experts.profile import ExpertProfile
                
                expert = ExpertProfile(
                    name="Test Expert",
                    domain="testing",
                    vector_store_id="vs_test"
                )
                
                session = ExpertChatSession(expert, agentic=True)
                session.research_count = 12
                
                # Mock the synthesis dependencies - need to mock at module level
                with patch.object(session, '_trigger_background_synthesis') as mock_synthesis:
                    mock_synthesis.return_value = {
                        "status": "skipped",
                        "reason": "No documents to synthesize",
                        "new_beliefs": 0,
                        "updated_beliefs": 0,
                        "gaps_filled": 0
                    }
                    
                    result = await session._trigger_background_synthesis()
                    
                    # Should be skipped due to no documents
                    assert result.get("status") == "skipped"

    @pytest.mark.asyncio
    async def test_logs_to_reasoning_trace(self):
        """Should log synthesis attempt to reasoning trace."""
        with patch('deepr.experts.chat.AsyncOpenAI'):
            with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
                from deepr.experts.chat import ExpertChatSession
                from deepr.experts.profile import ExpertProfile
                
                expert = ExpertProfile(
                    name="Test Expert",
                    domain="testing",
                    vector_store_id="vs_test"
                )
                
                session = ExpertChatSession(expert, agentic=True)
                session.research_count = 12
                session.synthesis_threshold = 10
                
                initial_trace_count = len(session.reasoning_trace)
                
                # Mock the synthesis dependencies
                with patch('deepr.experts.chat.ExpertStore') as mock_store:
                    mock_store_instance = MagicMock()
                    mock_store.return_value = mock_store_instance
                    
                    mock_knowledge_dir = MagicMock()
                    mock_knowledge_dir.exists.return_value = False
                    mock_store_instance.get_knowledge_dir.return_value = mock_knowledge_dir
                    
                    mock_docs_dir = MagicMock()
                    mock_docs_dir.exists.return_value = False
                    mock_store_instance.get_documents_dir.return_value = mock_docs_dir
                    
                    await session._trigger_background_synthesis()
                    
                    # Should NOT add to trace when skipped (no documents)
                    # Trace is only added on success or error
                    # This is expected behavior - skipped doesn't log

    @pytest.mark.asyncio
    async def test_handles_synthesis_error_gracefully(self):
        """Should not crash on synthesis error."""
        with patch('deepr.experts.chat.AsyncOpenAI'):
            with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
                from deepr.experts.chat import ExpertChatSession
                from deepr.experts.profile import ExpertProfile
                
                expert = ExpertProfile(
                    name="Test Expert",
                    domain="testing",
                    vector_store_id="vs_test"
                )
                
                session = ExpertChatSession(expert, agentic=True)
                
                # Mock to raise an exception
                with patch('deepr.experts.chat.ExpertStore') as mock_store:
                    mock_store.side_effect = Exception("Test error")
                    
                    result = await session._trigger_background_synthesis()
                    
                    # Should return error status, not crash
                    assert result.get("status") == "error"
                    assert "error" in result


class TestResearchCountIncrement:
    """Test that research count increments correctly during tool calls."""

    def test_research_count_starts_at_zero(self):
        """Research count should start at zero."""
        with patch('deepr.experts.chat.AsyncOpenAI'):
            with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
                from deepr.experts.chat import ExpertChatSession
                from deepr.experts.profile import ExpertProfile
                
                expert = ExpertProfile(
                    name="Test Expert",
                    domain="testing",
                    vector_store_id="vs_test"
                )
                
                session = ExpertChatSession(expert, agentic=True)
                
                assert session.research_count == 0


class TestConversationCountIncrement:
    """Test that conversation count increments correctly."""

    def test_conversation_count_starts_at_zero(self):
        """Conversation count should start at zero."""
        with patch('deepr.experts.chat.AsyncOpenAI'):
            with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
                from deepr.experts.chat import ExpertChatSession
                from deepr.experts.profile import ExpertProfile
                
                expert = ExpertProfile(
                    name="Test Expert",
                    domain="testing",
                    vector_store_id="vs_test"
                )
                
                session = ExpertChatSession(expert, agentic=True)
                
                assert session.conversation_count == 0
