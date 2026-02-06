"""
Tests for MCP Resource Handler.

Validates: Requirements 3.2, 3.3, 3.6, 4B.1, 4B.2, 4B.3
"""

import sys
from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

# Add deepr to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.mcp.state.job_manager import JobPhase
from deepr.mcp.state.resource_handler import (
    MCPResourceHandler,
    ResourceResponse,
    get_resource_handler,
    reset_resource_handler,
)


class TestResourceResponse:
    """Test ResourceResponse dataclass."""

    def test_success_with_data(self):
        """Response with data should be successful."""
        response = ResourceResponse(uri="deepr://campaigns/abc/status", data={"phase": "executing"})

        assert response.success is True
        assert response.error is None

    def test_failure_with_error(self):
        """Response with error should not be successful."""
        response = ResourceResponse(uri="deepr://campaigns/abc/status", data=None, error="Not found")

        assert response.success is False
        assert response.error == "Not found"


class TestMCPResourceHandler:
    """Test MCPResourceHandler functionality."""

    @pytest.fixture
    def handler(self, tmp_path):
        return MCPResourceHandler(reports_base=tmp_path / "reports", db_path=False)

    @pytest.mark.asyncio
    async def test_read_campaign_status(self, handler):
        """Should read campaign status resource."""
        # Create a job first
        await handler.jobs.create_job(job_id="test_123", goal="Test research", model="o4-mini")

        response = handler.read_resource("deepr://campaigns/test_123/status")

        assert response.success
        assert response.data["job_id"] == "test_123"
        assert response.data["phase"] == "queued"

    @pytest.mark.asyncio
    async def test_read_campaign_plan(self, handler):
        """Should read campaign plan resource."""
        await handler.jobs.create_job(job_id="test_123", goal="Test research", model="o4-mini")

        response = handler.read_resource("deepr://campaigns/test_123/plan")

        assert response.success
        assert response.data["goal"] == "Test research"
        assert response.data["model"] == "o4-mini"

    @pytest.mark.asyncio
    async def test_read_campaign_beliefs(self, handler):
        """Should read campaign beliefs resource."""
        await handler.jobs.create_job(job_id="test_123", goal="Test research")

        await handler.jobs.add_belief("test_123", "Test belief", 0.9)

        response = handler.read_resource("deepr://campaigns/test_123/beliefs")

        assert response.success
        assert response.data["belief_count"] == 1

    def test_read_expert_profile(self, handler):
        """Should read expert profile resource."""
        handler.experts.register_expert(
            expert_id="tech_expert", name="Tech Expert", domain="Technology", description="Expert in tech"
        )

        response = handler.read_resource("deepr://experts/tech_expert/profile")

        assert response.success
        assert response.data["name"] == "Tech Expert"
        assert response.data["domain"] == "Technology"

    def test_read_expert_beliefs(self, handler):
        """Should read expert beliefs resource."""
        handler.experts.register_expert(
            expert_id="tech_expert", name="Tech Expert", domain="Technology", description="Expert in tech"
        )
        handler.experts.add_belief("tech_expert", "AI is growing", 0.85)

        response = handler.read_resource("deepr://experts/tech_expert/beliefs")

        assert response.success
        assert response.data["belief_count"] == 1

    def test_read_expert_gaps(self, handler):
        """Should read expert gaps resource."""
        handler.experts.register_expert(
            expert_id="tech_expert", name="Tech Expert", domain="Technology", description="Expert in tech"
        )
        handler.experts.add_gap("tech_expert", "Quantum computing", "high")

        response = handler.read_resource("deepr://experts/tech_expert/gaps")

        assert response.success
        assert response.data["gap_count"] == 1

    def test_read_invalid_uri(self, handler):
        """Should return error for invalid URI."""
        response = handler.read_resource("invalid_uri")

        assert not response.success
        assert "Invalid resource URI" in response.error

    def test_read_nonexistent_job(self, handler):
        """Should return error for nonexistent job."""
        response = handler.read_resource("deepr://campaigns/nonexistent/status")

        assert not response.success
        assert "not found" in response.error.lower()

    def test_read_nonexistent_expert(self, handler):
        """Should return error for nonexistent expert."""
        response = handler.read_resource("deepr://experts/nonexistent/profile")

        assert not response.success
        assert "not found" in response.error.lower()

    @pytest.mark.asyncio
    async def test_list_resources(self, handler):
        """Should list all available resources."""
        await handler.jobs.create_job(job_id="job_1", goal="Test 1")
        handler.experts.register_expert("expert_1", "Expert 1", "Domain", "Desc")

        uris = handler.list_resources()

        # Should have 3 campaign resources + 3 expert resources
        assert len(uris) == 6
        assert "deepr://campaigns/job_1/status" in uris
        assert "deepr://experts/expert_1/profile" in uris

    @pytest.mark.asyncio
    async def test_list_resources_filtered(self, handler):
        """Should filter resources by type."""
        await handler.jobs.create_job(job_id="job_1", goal="Test 1")
        handler.experts.register_expert("expert_1", "Expert 1", "Domain", "Desc")

        campaign_uris = handler.list_resources("campaigns")
        expert_uris = handler.list_resources("experts")

        assert len(campaign_uris) == 3
        assert len(expert_uris) == 3
        assert all("campaigns" in uri for uri in campaign_uris)
        assert all("experts" in uri for uri in expert_uris)

    @pytest.mark.asyncio
    async def test_handle_subscribe(self, handler):
        """Should handle subscribe request."""

        async def callback(data):
            pass

        result = await handler.handle_subscribe("deepr://campaigns/test/status", callback)

        assert "subscription_id" in result
        assert result["uri"] == "deepr://campaigns/test/status"

    @pytest.mark.asyncio
    async def test_handle_subscribe_invalid_uri(self, handler):
        """Should return error for invalid subscribe URI."""

        async def callback(data):
            pass

        result = await handler.handle_subscribe("invalid", callback)

        assert "error" in result

    @pytest.mark.asyncio
    async def test_handle_unsubscribe(self, handler):
        """Should handle unsubscribe request."""

        async def callback(data):
            pass

        sub_result = await handler.handle_subscribe("deepr://campaigns/test/status", callback)

        unsub_result = await handler.handle_unsubscribe(sub_result["subscription_id"])

        assert unsub_result["success"] is True

    def test_get_resource_uri_for_job(self, handler):
        """Should return all URIs for a job."""
        uris = handler.get_resource_uri_for_job("test_123")

        assert uris["status"] == "deepr://campaigns/test_123/status"
        assert uris["plan"] == "deepr://campaigns/test_123/plan"
        assert uris["beliefs"] == "deepr://campaigns/test_123/beliefs"

    def test_get_resource_uri_for_expert(self, handler):
        """Should return all URIs for an expert."""
        uris = handler.get_resource_uri_for_expert("tech_expert")

        assert uris["profile"] == "deepr://experts/tech_expert/profile"
        assert uris["beliefs"] == "deepr://experts/tech_expert/beliefs"
        assert uris["gaps"] == "deepr://experts/tech_expert/gaps"


class TestSingleton:
    """Test singleton pattern."""

    def test_get_resource_handler_returns_same_instance(self):
        """get_resource_handler should return same instance."""
        reset_resource_handler()

        handler1 = get_resource_handler()
        handler2 = get_resource_handler()

        assert handler1 is handler2

    def test_reset_resource_handler(self):
        """reset_resource_handler should create new instance."""
        handler1 = get_resource_handler()
        reset_resource_handler()
        handler2 = get_resource_handler()

        assert handler1 is not handler2


class TestPropertyBased:
    """Property-based tests for resource handler."""

    @pytest.mark.asyncio
    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=50))
    @settings(max_examples=30)
    async def test_job_resources_accessible_after_creation(self, job_id: str):
        """
        Property: All job resources should be accessible after job creation.
        Validates: Requirements 3.2, 3.3
        """
        assume(job_id.strip())

        handler = MCPResourceHandler(db_path=False)
        await handler.jobs.create_job(job_id=job_id, goal="Test")

        # All three resources should be readable
        status = handler.read_resource(f"deepr://campaigns/{job_id}/status")
        plan = handler.read_resource(f"deepr://campaigns/{job_id}/plan")
        beliefs = handler.read_resource(f"deepr://campaigns/{job_id}/beliefs")

        assert status.success
        assert plan.success
        assert beliefs.success

    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=50))
    @settings(max_examples=30)
    def test_expert_resources_accessible_after_registration(self, expert_id: str):
        """
        Property: All expert resources should be accessible after registration.
        Validates: Requirements 4B.1, 4B.2, 4B.3
        """
        assume(expert_id.strip())

        handler = MCPResourceHandler(db_path=False)
        handler.experts.register_expert(expert_id=expert_id, name="Test", domain="Test", description="Test")

        # All three resources should be readable
        profile = handler.read_resource(f"deepr://experts/{expert_id}/profile")
        beliefs = handler.read_resource(f"deepr://experts/{expert_id}/beliefs")
        gaps = handler.read_resource(f"deepr://experts/{expert_id}/gaps")

        assert profile.success
        assert beliefs.success
        assert gaps.success

    @pytest.mark.asyncio
    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=50))
    @settings(max_examples=30)
    async def test_resource_uris_match_job_id(self, job_id: str):
        """
        Property: Resource URIs should contain the correct job_id.
        Validates: Requirements 3.6
        """
        assume(job_id.strip())

        handler = MCPResourceHandler(db_path=False)
        uris = handler.get_resource_uri_for_job(job_id)

        assert job_id in uris["status"]
        assert job_id in uris["plan"]
        assert job_id in uris["beliefs"]


class TestPersistenceIntegration:
    """Test persistence wiring in MCPResourceHandler."""

    @pytest.fixture
    def handler_with_db(self, tmp_path):
        return MCPResourceHandler(
            reports_base=tmp_path / "reports",
            db_path=tmp_path / "test_jobs.db",
        )

    def test_persistence_enabled(self, handler_with_db):
        """Handler should have persistence when db_path provided."""
        assert handler_with_db.persistence is not None

    def test_persistence_disabled(self, tmp_path):
        """Handler should skip persistence when db_path=False."""
        handler = MCPResourceHandler(reports_base=tmp_path / "reports", db_path=False)
        assert handler.persistence is None

    @pytest.mark.asyncio
    async def test_persist_job_saves_to_db(self, handler_with_db):
        """persist_job should save state to SQLite."""
        await handler_with_db.jobs.create_job(job_id="persist_test", goal="Test persistence")
        handler_with_db.persist_job("persist_test")

        # Verify in DB
        result = handler_with_db.persistence.load_job("persist_test")
        assert result is not None
        state, plan, beliefs = result
        assert state.job_id == "persist_test"
        assert plan.goal == "Test persistence"

    @pytest.mark.asyncio
    async def test_restore_jobs_on_init(self, tmp_path):
        """Jobs should be restored from SQLite on handler creation."""
        db_path = tmp_path / "restore_test.db"
        reports_base = tmp_path / "reports"

        # First handler: create and persist a job
        h1 = MCPResourceHandler(reports_base=reports_base, db_path=db_path)
        await h1.jobs.create_job(job_id="survive_restart", goal="Survive")
        await h1.jobs.update_phase("survive_restart", JobPhase.COMPLETED, progress=1.0)
        h1.persist_job("survive_restart")

        # Second handler: simulates restart
        h2 = MCPResourceHandler(reports_base=reports_base, db_path=db_path)
        state = h2.jobs.get_state("survive_restart")
        assert state is not None
        assert state.phase == JobPhase.COMPLETED

    @pytest.mark.asyncio
    async def test_incomplete_jobs_marked_failed_on_restart(self, tmp_path):
        """Incomplete jobs should be marked failed when handler restarts."""
        db_path = tmp_path / "restart_test.db"
        reports_base = tmp_path / "reports"

        # First handler: create an executing job
        h1 = MCPResourceHandler(reports_base=reports_base, db_path=db_path)
        await h1.jobs.create_job(job_id="was_running", goal="Running")
        await h1.jobs.update_phase("was_running", JobPhase.EXECUTING)
        h1.persist_job("was_running")

        # Second handler: simulates restart
        h2 = MCPResourceHandler(reports_base=reports_base, db_path=db_path)
        state = h2.jobs.get_state("was_running")
        assert state is not None
        assert state.phase == JobPhase.FAILED
        assert "restart" in state.error.lower()
