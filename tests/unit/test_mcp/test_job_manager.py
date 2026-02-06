"""
Tests for MCP Job Manager.

Validates: Requirements 3.2, 3.3, 3.6, 3B.4, 3B.6
"""

import asyncio
import sys
from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

# Add deepr to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.mcp.state.job_manager import (
    JobBeliefs,
    JobManager,
    JobPhase,
    JobPlan,
    JobState,
)
from deepr.mcp.state.subscriptions import SubscriptionManager


class TestJobState:
    """Test JobState dataclass."""

    def test_default_state(self):
        """Default state should be QUEUED with zero progress."""
        state = JobState(job_id="test_job")

        assert state.phase == JobPhase.QUEUED
        assert state.progress == 0.0
        assert state.cost_so_far == 0.0
        assert state.active_tasks == []

    def test_to_dict(self):
        """to_dict should serialize all fields."""
        state = JobState(
            job_id="test_job", phase=JobPhase.EXECUTING, progress=0.5, active_tasks=["Analyzing data"], cost_so_far=0.15
        )

        data = state.to_dict()

        assert data["job_id"] == "test_job"
        assert data["phase"] == "executing"
        assert data["progress"] == 0.5
        assert data["active_tasks"] == ["Analyzing data"]
        assert data["cost_so_far"] == 0.15


class TestJobPlan:
    """Test JobPlan dataclass."""

    def test_to_dict(self):
        """to_dict should serialize plan fields."""
        plan = JobPlan(
            job_id="test_job",
            goal="Research AI trends",
            steps=[{"step": 1, "action": "Search"}],
            estimated_cost=0.25,
            estimated_time="5 minutes",
            model="o4-mini",
        )

        data = plan.to_dict()

        assert data["job_id"] == "test_job"
        assert data["goal"] == "Research AI trends"
        assert len(data["steps"]) == 1
        assert data["estimated_cost"] == 0.25


class TestJobBeliefs:
    """Test JobBeliefs dataclass."""

    def test_to_dict(self):
        """to_dict should serialize beliefs."""
        beliefs = JobBeliefs(
            job_id="test_job",
            beliefs=[{"text": "Finding 1", "confidence": 0.9}],
            sources=["source1.com"],
            confidence=0.9,
        )

        data = beliefs.to_dict()

        assert data["job_id"] == "test_job"
        assert data["belief_count"] == 1
        assert data["confidence"] == 0.9


class TestJobManager:
    """Test JobManager functionality."""

    @pytest.fixture
    def manager(self):
        return JobManager()

    @pytest.mark.asyncio
    async def test_create_job(self, manager):
        """create_job should initialize job state."""
        state = await manager.create_job(
            job_id="test_123", goal="Research topic", model="o4-mini", estimated_cost=0.20, estimated_time="5 minutes"
        )

        assert state.job_id == "test_123"
        assert state.phase == JobPhase.QUEUED
        assert state.estimated_remaining == "5 minutes"

    @pytest.mark.asyncio
    async def test_create_job_initializes_plan(self, manager):
        """create_job should also create plan."""
        await manager.create_job(job_id="test_123", goal="Research topic", model="o4-mini")

        plan = manager.get_plan("test_123")

        assert plan is not None
        assert plan.goal == "Research topic"
        assert plan.model == "o4-mini"

    @pytest.mark.asyncio
    async def test_create_job_initializes_beliefs(self, manager):
        """create_job should also create empty beliefs."""
        await manager.create_job(job_id="test_123", goal="Research topic")

        beliefs = manager.get_beliefs("test_123")

        assert beliefs is not None
        assert beliefs.beliefs == []

    @pytest.mark.asyncio
    async def test_update_phase(self, manager):
        """update_phase should change job state."""
        await manager.create_job(job_id="test_123", goal="Test")

        state = await manager.update_phase(
            job_id="test_123", phase=JobPhase.EXECUTING, progress=0.3, active_tasks=["Task 1"], cost_so_far=0.05
        )

        assert state.phase == JobPhase.EXECUTING
        assert state.progress == 0.3
        assert state.active_tasks == ["Task 1"]
        assert state.cost_so_far == 0.05

    @pytest.mark.asyncio
    async def test_update_phase_clamps_progress(self, manager):
        """update_phase should clamp progress to 0.0-1.0."""
        await manager.create_job(job_id="test_123", goal="Test")

        # Test over 1.0
        state = await manager.update_phase(job_id="test_123", phase=JobPhase.EXECUTING, progress=1.5)
        assert state.progress == 1.0

        # Test under 0.0
        state = await manager.update_phase(job_id="test_123", phase=JobPhase.EXECUTING, progress=-0.5)
        assert state.progress == 0.0

    @pytest.mark.asyncio
    async def test_update_phase_nonexistent_returns_none(self, manager):
        """update_phase on nonexistent job should return None."""
        result = await manager.update_phase(job_id="nonexistent", phase=JobPhase.EXECUTING)

        assert result is None

    @pytest.mark.asyncio
    async def test_add_belief(self, manager):
        """add_belief should add to job beliefs."""
        await manager.create_job(job_id="test_123", goal="Test")

        result = await manager.add_belief(
            job_id="test_123", belief="AI is transforming industries", confidence=0.85, source="research.com"
        )

        assert result is True

        beliefs = manager.get_beliefs("test_123")
        assert len(beliefs.beliefs) == 1
        assert beliefs.beliefs[0]["text"] == "AI is transforming industries"
        assert beliefs.beliefs[0]["confidence"] == 0.85
        assert "research.com" in beliefs.sources

    @pytest.mark.asyncio
    async def test_add_belief_updates_confidence(self, manager):
        """add_belief should update overall confidence."""
        await manager.create_job(job_id="test_123", goal="Test")

        await manager.add_belief("test_123", "Belief 1", 0.8)
        await manager.add_belief("test_123", "Belief 2", 0.6)

        beliefs = manager.get_beliefs("test_123")

        # Average of 0.8 and 0.6
        assert beliefs.confidence == pytest.approx(0.7, rel=0.01)

    @pytest.mark.asyncio
    async def test_update_plan(self, manager):
        """update_plan should update job plan steps."""
        await manager.create_job(job_id="test_123", goal="Test")

        steps = [{"step": 1, "action": "Search web"}, {"step": 2, "action": "Analyze results"}]

        result = await manager.update_plan("test_123", steps)

        assert result is True

        plan = manager.get_plan("test_123")
        assert len(plan.steps) == 2

    @pytest.mark.asyncio
    async def test_list_jobs(self, manager):
        """list_jobs should return all or filtered jobs."""
        await manager.create_job(job_id="job_1", goal="Test 1")
        await manager.create_job(job_id="job_2", goal="Test 2")

        await manager.update_phase("job_1", JobPhase.EXECUTING)

        all_jobs = manager.list_jobs()
        assert len(all_jobs) == 2

        executing_jobs = manager.list_jobs(phase=JobPhase.EXECUTING)
        assert len(executing_jobs) == 1
        assert executing_jobs[0].job_id == "job_1"

        queued_jobs = manager.list_jobs(phase=JobPhase.QUEUED)
        assert len(queued_jobs) == 1
        assert queued_jobs[0].job_id == "job_2"

    @pytest.mark.asyncio
    async def test_remove_job(self, manager):
        """remove_job should remove job and associated data."""
        await manager.create_job(job_id="test_123", goal="Test")

        result = await manager.remove_job("test_123")

        assert result is True
        assert manager.get_state("test_123") is None
        assert manager.get_plan("test_123") is None
        assert manager.get_beliefs("test_123") is None

    @pytest.mark.asyncio
    async def test_remove_nonexistent_returns_false(self, manager):
        """remove_job on nonexistent job should return False."""
        result = await manager.remove_job("nonexistent")

        assert result is False


class TestJobManagerSubscriptions:
    """Test JobManager integration with subscriptions."""

    @pytest.mark.asyncio
    async def test_create_job_emits_status(self):
        """create_job should emit status update."""
        received = []

        async def callback(data):
            received.append(data)

        sub_manager = SubscriptionManager()
        manager = JobManager(sub_manager)

        await sub_manager.subscribe("deepr://campaigns/test_123/status", callback)

        await manager.create_job(job_id="test_123", goal="Test")

        # Allow background task to complete
        await asyncio.sleep(0.1)

        assert len(received) == 1
        assert received[0]["params"]["uri"] == "deepr://campaigns/test_123/status"

    @pytest.mark.asyncio
    async def test_update_phase_emits_status(self):
        """update_phase should emit status update."""
        received = []

        async def callback(data):
            received.append(data)

        sub_manager = SubscriptionManager()
        manager = JobManager(sub_manager)

        await manager.create_job(job_id="test_123", goal="Test")

        await sub_manager.subscribe("deepr://campaigns/test_123/status", callback)

        await manager.update_phase("test_123", JobPhase.EXECUTING, progress=0.5)

        # Allow background task to complete
        await asyncio.sleep(0.1)

        assert len(received) >= 1
        # Last notification should have executing phase
        last = received[-1]
        assert last["params"]["data"]["phase"] == "executing"

    @pytest.mark.asyncio
    async def test_add_belief_emits_beliefs_update(self):
        """add_belief should emit beliefs update."""
        received = []

        async def callback(data):
            received.append(data)

        sub_manager = SubscriptionManager()
        manager = JobManager(sub_manager)

        await manager.create_job(job_id="test_123", goal="Test")

        await sub_manager.subscribe("deepr://campaigns/test_123/beliefs", callback)

        await manager.add_belief("test_123", "Test belief", 0.9)

        # Allow background task to complete
        await asyncio.sleep(0.1)

        assert len(received) == 1
        assert received[0]["params"]["uri"] == "deepr://campaigns/test_123/beliefs"

    @pytest.mark.asyncio
    async def test_update_plan_emits_plan_update(self):
        """update_plan should emit plan update."""
        received = []

        async def callback(data):
            received.append(data)

        sub_manager = SubscriptionManager()
        manager = JobManager(sub_manager)

        await manager.create_job(job_id="test_123", goal="Test")

        await sub_manager.subscribe("deepr://campaigns/test_123/plan", callback)

        await manager.update_plan("test_123", [{"step": 1}])

        # Allow background task to complete
        await asyncio.sleep(0.1)

        assert len(received) == 1
        assert received[0]["params"]["uri"] == "deepr://campaigns/test_123/plan"


class TestPropertyBased:
    """Property-based tests for job manager."""

    @pytest.mark.asyncio
    @given(st.floats(min_value=-10.0, max_value=10.0))
    @settings(max_examples=50)
    async def test_progress_always_clamped(self, progress: float):
        """
        Property: Progress should always be clamped to 0.0-1.0.
        Validates: Requirements 3B.4
        """
        manager = JobManager()
        await manager.create_job(job_id="test", goal="Test")

        state = await manager.update_phase(job_id="test", phase=JobPhase.EXECUTING, progress=progress)

        assert 0.0 <= state.progress <= 1.0

    @pytest.mark.asyncio
    @given(st.lists(st.floats(min_value=0.0, max_value=1.0), min_size=1, max_size=10))
    @settings(max_examples=30)
    async def test_belief_confidence_is_average(self, confidences: list[float]):
        """
        Property: Overall confidence should be average of belief confidences.
        Validates: Requirements 3B.6
        """
        assume(all(0.0 <= c <= 1.0 for c in confidences))

        manager = JobManager()
        await manager.create_job(job_id="test", goal="Test")

        for i, conf in enumerate(confidences):
            await manager.add_belief("test", f"Belief {i}", conf)

        beliefs = manager.get_beliefs("test")
        expected_avg = sum(confidences) / len(confidences)

        assert beliefs.confidence == pytest.approx(expected_avg, rel=0.01)

    @pytest.mark.asyncio
    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=50))
    @settings(max_examples=30)
    async def test_job_id_preserved(self, job_id: str):
        """
        Property: Job ID should be preserved through all operations.
        Validates: Requirements 3.2
        """
        assume(job_id.strip())

        manager = JobManager()
        state = await manager.create_job(job_id=job_id, goal="Test")

        assert state.job_id == job_id
        assert manager.get_state(job_id).job_id == job_id
        assert manager.get_plan(job_id).job_id == job_id
        assert manager.get_beliefs(job_id).job_id == job_id
