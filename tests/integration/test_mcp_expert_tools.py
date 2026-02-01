"""
Integration tests for MCP Expert Tools.

Tests the MCP server's expert-related tools:
- list_experts: List available domain experts
- get_expert_info: Get detailed expert information
- query_expert: Query a domain expert with a question

Validates: Requirements 9.1, 9.2, 9.3, 9.4 from Task 5.3

These tests use mocked providers to avoid API costs while testing
the full integration path through the MCP server.
"""

import sys
from pathlib import Path
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime

# Add deepr to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from deepr.mcp.server import DeeprMCPServer


class TestMCPListExperts:
    """Integration tests for list_experts MCP tool."""

    @pytest.fixture
    def server(self):
        """Create MCP server instance."""
        return DeeprMCPServer()

    @pytest.mark.asyncio
    async def test_list_experts_empty_store(self, server):
        """list_experts should return empty list when no experts exist."""
        with patch.object(server.store, 'list_all', return_value=[]):
            result = await server.list_experts()
        
        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_list_experts_returns_expert_summaries(self, server):
        """list_experts should return summaries for all experts."""
        mock_experts = [
            {
                "name": "tech_expert",
                "domain": "Technology",
                "description": "Expert in tech trends",
                "stats": {"documents": 50, "conversations": 10}
            },
            {
                "name": "finance_expert",
                "domain": "Finance",
                "description": "Expert in financial markets",
                "stats": {"documents": 30, "conversations": 5}
            }
        ]
        
        with patch.object(server.store, 'list_all', return_value=mock_experts):
            result = await server.list_experts()
        
        assert len(result) == 2
        assert result[0]["name"] == "tech_expert"
        assert result[0]["domain"] == "Technology"
        assert result[0]["documents"] == 50
        assert result[1]["name"] == "finance_expert"

    @pytest.mark.asyncio
    async def test_list_experts_handles_store_error(self, server):
        """list_experts should return error dict on store failure."""
        with patch.object(server.store, 'list_all', side_effect=Exception("Store error")):
            result = await server.list_experts()
        
        assert len(result) == 1
        assert "error" in result[0]
        assert "Store error" in result[0]["error"]

    @pytest.mark.asyncio
    async def test_list_experts_includes_required_fields(self, server):
        """list_experts should include all required fields in response."""
        mock_experts = [
            {
                "name": "test_expert",
                "domain": "Testing",
                "description": "Test expert",
                "stats": {"documents": 10, "conversations": 2}
            }
        ]
        
        with patch.object(server.store, 'list_all', return_value=mock_experts):
            result = await server.list_experts()
        
        assert len(result) == 1
        expert = result[0]
        
        # Required fields per MCP schema
        assert "name" in expert
        assert "domain" in expert
        assert "description" in expert
        assert "documents" in expert
        assert "conversations" in expert


class TestMCPGetExpertInfo:
    """Integration tests for get_expert_info MCP tool."""

    @pytest.fixture
    def server(self):
        """Create MCP server instance."""
        return DeeprMCPServer()

    @pytest.fixture
    def mock_expert(self):
        """Create a mock expert profile."""
        expert = Mock()
        expert.name = "tech_expert"
        expert.domain = "Technology"
        expert.description = "Expert in tech trends"
        expert.vector_store_id = "vs_123"
        expert.total_documents = 50
        expert.stats = {"conversations": 10, "total_cost": 5.25}
        expert.research_jobs = ["job1", "job2"]
        expert.created_at = datetime(2025, 1, 1, 12, 0, 0)
        expert.last_knowledge_refresh = datetime(2025, 1, 15, 12, 0, 0)
        return expert

    @pytest.mark.asyncio
    async def test_get_expert_info_returns_details(self, server, mock_expert):
        """get_expert_info should return detailed expert information."""
        with patch.object(server.store, 'load', return_value=mock_expert):
            result = await server.get_expert_info("tech_expert")
        
        assert result["name"] == "tech_expert"
        assert result["domain"] == "Technology"
        assert result["description"] == "Expert in tech trends"
        assert result["vector_store_id"] == "vs_123"
        assert result["stats"]["documents"] == 50
        assert result["stats"]["conversations"] == 10
        assert result["stats"]["research_jobs"] == 2
        assert result["stats"]["total_cost"] == 5.25

    @pytest.mark.asyncio
    async def test_get_expert_info_not_found(self, server):
        """get_expert_info should return error for non-existent expert."""
        with patch.object(server.store, 'load', return_value=None):
            result = await server.get_expert_info("nonexistent")
        
        assert "error" in result
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_get_expert_info_handles_exception(self, server):
        """get_expert_info should handle exceptions gracefully."""
        with patch.object(server.store, 'load', side_effect=Exception("Load error")):
            result = await server.get_expert_info("tech_expert")
        
        assert "error" in result
        assert "Load error" in result["error"]

    @pytest.mark.asyncio
    async def test_get_expert_info_includes_timestamps(self, server, mock_expert):
        """get_expert_info should include ISO-formatted timestamps."""
        with patch.object(server.store, 'load', return_value=mock_expert):
            result = await server.get_expert_info("tech_expert")
        
        assert result["created_at"] == "2025-01-01T12:00:00"
        assert result["last_knowledge_refresh"] == "2025-01-15T12:00:00"

    @pytest.mark.asyncio
    async def test_get_expert_info_handles_missing_timestamps(self, server):
        """get_expert_info should handle experts without timestamps."""
        expert = Mock()
        expert.name = "new_expert"
        expert.domain = "Test"
        expert.description = "New expert"
        expert.vector_store_id = None
        expert.total_documents = 0
        expert.stats = {}
        expert.research_jobs = []
        expert.created_at = None
        expert.last_knowledge_refresh = None
        
        with patch.object(server.store, 'load', return_value=expert):
            result = await server.get_expert_info("new_expert")
        
        assert result["created_at"] is None
        assert result["last_knowledge_refresh"] is None


class TestMCPQueryExpert:
    """Integration tests for query_expert MCP tool."""

    @pytest.fixture
    def server(self):
        """Create MCP server instance."""
        return DeeprMCPServer()

    @pytest.fixture
    def mock_expert(self):
        """Create a mock expert profile."""
        expert = Mock()
        expert.name = "tech_expert"
        expert.domain = "Technology"
        return expert

    @pytest.mark.asyncio
    async def test_query_expert_returns_answer(self, server, mock_expert):
        """query_expert should return expert's answer."""
        mock_session = AsyncMock()
        mock_session.send_message = AsyncMock(return_value="AI is transforming industries.")
        mock_session.get_session_summary = Mock(return_value={
            "cost_accumulated": 0.05,
            "budget_remaining": None,
            "research_jobs_triggered": 0
        })
        
        with patch.object(server.store, 'load', return_value=mock_expert):
            with patch('deepr.mcp.server.ExpertChatSession', return_value=mock_session):
                result = await server.query_expert("tech_expert", "What is AI?")
        
        assert result["answer"] == "AI is transforming industries."
        assert result["expert"] == "tech_expert"
        assert result["cost"] == 0.05

    @pytest.mark.asyncio
    async def test_query_expert_not_found(self, server):
        """query_expert should return error for non-existent expert."""
        with patch.object(server.store, 'load', return_value=None):
            result = await server.query_expert("nonexistent", "Question?")
        
        assert "error" in result
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_query_expert_with_budget(self, server, mock_expert):
        """query_expert should pass budget to session when agentic."""
        mock_session = AsyncMock()
        mock_session.send_message = AsyncMock(return_value="Answer")
        mock_session.get_session_summary = Mock(return_value={
            "cost_accumulated": 0.10,
            "budget_remaining": 0.90,
            "research_jobs_triggered": 1
        })
        
        with patch.object(server.store, 'load', return_value=mock_expert):
            with patch('deepr.mcp.server.ExpertChatSession', return_value=mock_session) as mock_cls:
                result = await server.query_expert(
                    "tech_expert",
                    "Research AI trends",
                    budget=1.0,
                    agentic=True
                )
        
        # Verify session was created with budget and agentic mode
        mock_cls.assert_called_once()
        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs["budget"] == 1.0
        assert call_kwargs["agentic"] is True
        
        assert result["budget_remaining"] == 0.90
        assert result["research_triggered"] == 1

    @pytest.mark.asyncio
    async def test_query_expert_non_agentic_no_budget(self, server, mock_expert):
        """query_expert should not pass budget when not agentic."""
        mock_session = AsyncMock()
        mock_session.send_message = AsyncMock(return_value="Answer")
        mock_session.get_session_summary = Mock(return_value={
            "cost_accumulated": 0.02,
            "budget_remaining": None,
            "research_jobs_triggered": 0
        })
        
        with patch.object(server.store, 'load', return_value=mock_expert):
            with patch('deepr.mcp.server.ExpertChatSession', return_value=mock_session) as mock_cls:
                result = await server.query_expert(
                    "tech_expert",
                    "Simple question",
                    budget=1.0,
                    agentic=False
                )
        
        # Verify session was created without budget
        mock_cls.assert_called_once()
        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs["budget"] is None
        assert call_kwargs["agentic"] is False

    @pytest.mark.asyncio
    async def test_query_expert_handles_session_error(self, server, mock_expert):
        """query_expert should handle session errors gracefully."""
        mock_session = AsyncMock()
        mock_session.send_message = AsyncMock(side_effect=Exception("Session error"))
        
        with patch.object(server.store, 'load', return_value=mock_expert):
            with patch('deepr.mcp.server.ExpertChatSession', return_value=mock_session):
                result = await server.query_expert("tech_expert", "Question?")
        
        assert "error" in result
        assert "Session error" in result["error"]


class TestMCPAgenticResearch:
    """Integration tests for agentic research mode with experts."""

    @pytest.fixture
    def server(self):
        """Create MCP server instance."""
        return DeeprMCPServer()

    @pytest.fixture
    def mock_expert(self):
        """Create a mock expert profile."""
        expert = Mock()
        expert.name = "research_expert"
        expert.domain = "Research"
        return expert

    @pytest.mark.asyncio
    async def test_agentic_research_requires_expert(self, server):
        """agentic_research should require an expert name."""
        # Mock cost safety to allow the operation
        with patch('deepr.experts.cost_safety.get_cost_safety_manager') as mock_csm:
            mock_manager = Mock()
            mock_manager.check_operation = Mock(return_value=(True, None, None))
            mock_csm.return_value = mock_manager
            
            result = await server.deepr_agentic_research(
                goal="Research AI trends",
                expert_name=None,
                budget=5.0
            )
        
        assert "status" in result
        assert result["status"] == "planned"
        assert "expert" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_agentic_research_with_expert(self, server, mock_expert):
        """agentic_research should start workflow with valid expert."""
        mock_session = AsyncMock()
        mock_session.send_message = AsyncMock(return_value="Starting research on AI trends...")
        
        with patch.object(server.store, 'load', return_value=mock_expert):
            with patch('deepr.mcp.server.ExpertChatSession', return_value=mock_session):
                with patch('deepr.experts.cost_safety.get_cost_safety_manager') as mock_csm:
                    mock_manager = Mock()
                    mock_manager.check_operation = Mock(return_value=(True, None, None))
                    mock_manager.get_spending_summary = Mock(return_value={
                        "daily": {"spent": 1.0, "remaining": 9.0, "limit": 10.0}
                    })
                    mock_csm.return_value = mock_manager
                    
                    result = await server.deepr_agentic_research(
                        goal="Research AI trends",
                        expert_name="research_expert",
                        budget=5.0
                    )
        
        assert result["status"] == "in_progress"
        assert result["expert_name"] == "research_expert"
        assert "workflow_id" in result
        assert result["budget_allocated"] == 5.0

    @pytest.mark.asyncio
    async def test_agentic_research_budget_capped(self, server, mock_expert):
        """agentic_research should cap budget at maximum."""
        with patch('deepr.experts.cost_safety.get_cost_safety_manager') as mock_csm:
            mock_manager = Mock()
            mock_manager.check_operation = Mock(return_value=(True, None, None))
            mock_csm.return_value = mock_manager
            
            # Request budget exceeding max
            result = await server.deepr_agentic_research(
                goal="Research",
                expert_name="research_expert",
                budget=100.0  # Way over max
            )
        
        assert "error" in result
        assert "exceeds maximum" in result["error"]

    @pytest.mark.asyncio
    async def test_agentic_research_blocked_by_cost_safety(self, server, mock_expert):
        """agentic_research should respect cost safety limits."""
        with patch('deepr.experts.cost_safety.get_cost_safety_manager') as mock_csm:
            mock_manager = Mock()
            mock_manager.check_operation = Mock(return_value=(False, "Daily limit exceeded", None))
            mock_manager.get_spending_summary = Mock(return_value={
                "daily": {"spent": 10.0, "remaining": 0.0, "limit": 10.0}
            })
            mock_csm.return_value = mock_manager
            
            result = await server.deepr_agentic_research(
                goal="Research",
                expert_name="research_expert",
                budget=5.0
            )
        
        assert "error" in result
        assert "blocked" in result["error"].lower()


class TestMCPServerIntegration:
    """End-to-end integration tests for MCP server."""

    @pytest.fixture
    def server(self):
        """Create MCP server instance."""
        return DeeprMCPServer()

    @pytest.mark.asyncio
    async def test_full_expert_workflow(self, server):
        """Test complete workflow: list -> info -> query."""
        # Setup mock expert
        mock_expert = Mock()
        mock_expert.name = "workflow_expert"
        mock_expert.domain = "Workflow"
        mock_expert.description = "Test workflow expert"
        mock_expert.vector_store_id = "vs_test"
        mock_expert.total_documents = 10
        mock_expert.stats = {"conversations": 5, "total_cost": 1.0}
        mock_expert.research_jobs = []
        mock_expert.created_at = datetime.now()
        mock_expert.last_knowledge_refresh = None
        
        mock_experts_list = [{
            "name": "workflow_expert",
            "domain": "Workflow",
            "description": "Test workflow expert",
            "stats": {"documents": 10, "conversations": 5}
        }]
        
        mock_session = AsyncMock()
        mock_session.send_message = AsyncMock(return_value="Workflow answer")
        mock_session.get_session_summary = Mock(return_value={
            "cost_accumulated": 0.03,
            "budget_remaining": None,
            "research_jobs_triggered": 0
        })
        
        # Step 1: List experts
        with patch.object(server.store, 'list_all', return_value=mock_experts_list):
            experts = await server.list_experts()
        
        assert len(experts) == 1
        expert_name = experts[0]["name"]
        
        # Step 2: Get expert info
        with patch.object(server.store, 'load', return_value=mock_expert):
            info = await server.get_expert_info(expert_name)
        
        assert info["name"] == expert_name
        assert info["stats"]["documents"] == 10
        
        # Step 3: Query expert
        with patch.object(server.store, 'load', return_value=mock_expert):
            with patch('deepr.mcp.server.ExpertChatSession', return_value=mock_session):
                response = await server.query_expert(expert_name, "Test question")
        
        assert response["answer"] == "Workflow answer"
        assert response["expert"] == expert_name
        assert response["cost"] == 0.03

    @pytest.mark.asyncio
    async def test_error_propagation(self, server):
        """Test that errors propagate correctly through the stack."""
        # Test list_experts error
        with patch.object(server.store, 'list_all', side_effect=RuntimeError("DB connection failed")):
            result = await server.list_experts()
        assert "error" in result[0]
        
        # Test get_expert_info error
        with patch.object(server.store, 'load', side_effect=RuntimeError("Load failed")):
            result = await server.get_expert_info("test")
        assert "error" in result
        
        # Test query_expert error
        with patch.object(server.store, 'load', side_effect=RuntimeError("Query failed")):
            result = await server.query_expert("test", "question")
        assert "error" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
