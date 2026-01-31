"""
Tests for MCP Expert Resources.

Validates: Requirements 4B.1, 4B.2, 4B.3, 4B.6
"""

import sys
from pathlib import Path

import pytest
from hypothesis import given, strategies as st, settings, assume, HealthCheck

# Add deepr to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.mcp.state.expert_resources import (
    ExpertProfile,
    ExpertBelief,
    ExpertBeliefs,
    KnowledgeGap,
    ExpertGaps,
    ExpertResourceManager,
)


class TestExpertProfile:
    """Test ExpertProfile dataclass."""
    
    def test_to_dict(self):
        """to_dict should serialize all fields."""
        profile = ExpertProfile(
            expert_id="tech_expert",
            name="Tech Expert",
            domain="Technology",
            description="Expert in tech trends",
            document_count=50,
            conversation_count=10,
            total_cost=5.25,
            capabilities=["analysis", "forecasting"]
        )
        
        data = profile.to_dict()
        
        assert data["expert_id"] == "tech_expert"
        assert data["name"] == "Tech Expert"
        assert data["domain"] == "Technology"
        assert data["document_count"] == 50
        assert data["capabilities"] == ["analysis", "forecasting"]


class TestExpertBeliefs:
    """Test ExpertBeliefs dataclass."""
    
    def test_add_belief(self):
        """add_belief should add and recalculate confidence."""
        beliefs = ExpertBeliefs(expert_id="test")
        
        beliefs.add_belief("AI is growing", 0.9, "source1.com")
        
        assert len(beliefs.beliefs) == 1
        assert beliefs.beliefs[0].text == "AI is growing"
        assert beliefs.beliefs[0].confidence == 0.9
        assert beliefs.overall_confidence == 0.9
    
    def test_confidence_recalculation(self):
        """Overall confidence should be average of beliefs."""
        beliefs = ExpertBeliefs(expert_id="test")
        
        beliefs.add_belief("Belief 1", 0.8)
        beliefs.add_belief("Belief 2", 0.6)
        beliefs.add_belief("Belief 3", 0.7)
        
        # Average of 0.8, 0.6, 0.7 = 0.7
        assert beliefs.overall_confidence == pytest.approx(0.7, rel=0.01)
    
    def test_to_dict(self):
        """to_dict should serialize beliefs."""
        beliefs = ExpertBeliefs(expert_id="test")
        beliefs.add_belief("Test belief", 0.85, "source.com")
        
        data = beliefs.to_dict()
        
        assert data["expert_id"] == "test"
        assert data["belief_count"] == 1
        assert len(data["beliefs"]) == 1
        assert data["beliefs"][0]["text"] == "Test belief"


class TestExpertGaps:
    """Test ExpertGaps dataclass."""
    
    def test_add_gap(self):
        """add_gap should add knowledge gap."""
        gaps = ExpertGaps(expert_id="test")
        
        gaps.add_gap(
            topic="Quantum computing",
            severity="high",
            suggested_research="Research quantum algorithms"
        )
        
        assert len(gaps.gaps) == 1
        assert gaps.gaps[0].topic == "Quantum computing"
        assert gaps.gaps[0].severity == "high"
    
    def test_to_dict(self):
        """to_dict should serialize gaps with counts."""
        gaps = ExpertGaps(expert_id="test")
        gaps.add_gap("Topic 1", "high")
        gaps.add_gap("Topic 2", "medium")
        gaps.add_gap("Topic 3", "high")
        
        data = gaps.to_dict()
        
        assert data["expert_id"] == "test"
        assert data["gap_count"] == 3
        assert data["high_priority_count"] == 2


class TestExpertResourceManager:
    """Test ExpertResourceManager functionality."""
    
    @pytest.fixture
    def manager(self):
        return ExpertResourceManager()
    
    def test_register_expert(self, manager):
        """register_expert should create profile and associated resources."""
        profile = manager.register_expert(
            expert_id="tech_expert",
            name="Tech Expert",
            domain="Technology",
            description="Expert in tech"
        )
        
        assert profile.expert_id == "tech_expert"
        assert manager.get_profile("tech_expert") is not None
        assert manager.get_beliefs("tech_expert") is not None
        assert manager.get_gaps("tech_expert") is not None
    
    def test_add_belief(self, manager):
        """add_belief should add to expert beliefs."""
        manager.register_expert(
            expert_id="test",
            name="Test",
            domain="Test",
            description="Test"
        )
        
        result = manager.add_belief(
            expert_id="test",
            text="Test belief",
            confidence=0.9,
            source="source.com"
        )
        
        assert result is True
        
        beliefs = manager.get_beliefs("test")
        assert len(beliefs.beliefs) == 1
    
    def test_add_belief_nonexistent_returns_false(self, manager):
        """add_belief on nonexistent expert should return False."""
        result = manager.add_belief(
            expert_id="nonexistent",
            text="Test",
            confidence=0.5
        )
        
        assert result is False
    
    def test_add_gap(self, manager):
        """add_gap should add to expert gaps."""
        manager.register_expert(
            expert_id="test",
            name="Test",
            domain="Test",
            description="Test"
        )
        
        result = manager.add_gap(
            expert_id="test",
            topic="Missing knowledge",
            severity="high",
            suggested_research="Research this topic"
        )
        
        assert result is True
        
        gaps = manager.get_gaps("test")
        assert len(gaps.gaps) == 1
    
    def test_update_profile_stats(self, manager):
        """update_profile_stats should update profile."""
        manager.register_expert(
            expert_id="test",
            name="Test",
            domain="Test",
            description="Test"
        )
        
        result = manager.update_profile_stats(
            expert_id="test",
            document_count=100,
            conversation_count=25,
            total_cost=10.50
        )
        
        assert result is True
        
        profile = manager.get_profile("test")
        assert profile.document_count == 100
        assert profile.conversation_count == 25
        assert profile.total_cost == 10.50
    
    def test_list_experts(self, manager):
        """list_experts should return all registered experts."""
        manager.register_expert("expert_1", "Expert 1", "Domain 1", "Desc 1")
        manager.register_expert("expert_2", "Expert 2", "Domain 2", "Desc 2")
        
        experts = manager.list_experts()
        
        assert len(experts) == 2
    
    def test_remove_expert(self, manager):
        """remove_expert should remove expert and all resources."""
        manager.register_expert("test", "Test", "Test", "Test")
        
        result = manager.remove_expert("test")
        
        assert result is True
        assert manager.get_profile("test") is None
        assert manager.get_beliefs("test") is None
        assert manager.get_gaps("test") is None
    
    def test_get_resource_uri(self, manager):
        """get_resource_uri should return correct URI."""
        uri = manager.get_resource_uri("tech_expert", "profile")
        assert uri == "deepr://experts/tech_expert/profile"
        
        uri = manager.get_resource_uri("tech_expert", "beliefs")
        assert uri == "deepr://experts/tech_expert/beliefs"
        
        uri = manager.get_resource_uri("tech_expert", "gaps")
        assert uri == "deepr://experts/tech_expert/gaps"
    
    def test_resolve_uri_profile(self, manager):
        """resolve_uri should return profile data."""
        manager.register_expert(
            expert_id="test",
            name="Test Expert",
            domain="Testing",
            description="Test description"
        )
        
        data = manager.resolve_uri("deepr://experts/test/profile")
        
        assert data is not None
        assert data["name"] == "Test Expert"
        assert data["domain"] == "Testing"
    
    def test_resolve_uri_beliefs(self, manager):
        """resolve_uri should return beliefs data."""
        manager.register_expert("test", "Test", "Test", "Test")
        manager.add_belief("test", "Test belief", 0.9)
        
        data = manager.resolve_uri("deepr://experts/test/beliefs")
        
        assert data is not None
        assert data["belief_count"] == 1
    
    def test_resolve_uri_gaps(self, manager):
        """resolve_uri should return gaps data."""
        manager.register_expert("test", "Test", "Test", "Test")
        manager.add_gap("test", "Missing topic", "high")
        
        data = manager.resolve_uri("deepr://experts/test/gaps")
        
        assert data is not None
        assert data["gap_count"] == 1
    
    def test_resolve_uri_invalid_returns_none(self, manager):
        """resolve_uri with invalid URI should return None."""
        assert manager.resolve_uri("invalid") is None
        assert manager.resolve_uri("deepr://experts/nonexistent/profile") is None
        assert manager.resolve_uri("deepr://campaigns/test/status") is None


class TestExpertResourceValidation:
    """Test defensive validation in expert resources."""
    
    def test_belief_confidence_clamped_above_one(self):
        """Confidence values above 1.0 should be clamped to 1.0."""
        beliefs = ExpertBeliefs(expert_id="test")
        beliefs.add_belief("Test belief", 1.5, "source.com")
        
        assert beliefs.beliefs[0].confidence == 1.0
    
    def test_belief_confidence_clamped_below_zero(self):
        """Confidence values below 0.0 should be clamped to 0.0."""
        beliefs = ExpertBeliefs(expert_id="test")
        beliefs.add_belief("Test belief", -0.5, "source.com")
        
        assert beliefs.beliefs[0].confidence == 0.0
    
    def test_manager_add_belief_rejects_empty_text(self):
        """add_belief should reject empty text."""
        manager = ExpertResourceManager()
        manager.register_expert("test", "Test", "Test", "Test")
        
        result = manager.add_belief("test", "", 0.9)
        assert result is False
    
    def test_manager_add_belief_rejects_whitespace_text(self):
        """add_belief should reject whitespace-only text."""
        manager = ExpertResourceManager()
        manager.register_expert("test", "Test", "Test", "Test")
        
        result = manager.add_belief("test", "   ", 0.9)
        assert result is False
    
    @given(st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=50)
    def test_confidence_always_clamped_to_valid_range(self, confidence: float):
        """
        Property: Confidence is always clamped to [0.0, 1.0].
        """
        beliefs = ExpertBeliefs(expert_id="test")
        beliefs.add_belief("Test belief", confidence)
        
        assert 0.0 <= beliefs.beliefs[0].confidence <= 1.0


class TestPropertyBased:
    """Property-based tests for expert resources."""
    
    @given(st.lists(st.floats(min_value=0.0, max_value=1.0), min_size=1, max_size=20))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_belief_confidence_is_average(self, confidences: list[float]):
        """
        Property: Overall confidence should be average of belief confidences.
        Validates: Requirements 4B.6
        """
        assume(all(0.0 <= c <= 1.0 for c in confidences))
        
        beliefs = ExpertBeliefs(expert_id="test")
        
        for i, conf in enumerate(confidences):
            beliefs.add_belief(f"Belief {i}", conf)
        
        expected_avg = sum(confidences) / len(confidences)
        
        assert beliefs.overall_confidence == pytest.approx(expected_avg, rel=0.01)
    
    @given(
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=50),
        st.sampled_from(["profile", "beliefs", "gaps"])
    )
    @settings(max_examples=50)
    def test_uri_generation_and_resolution(self, expert_id: str, resource_type: str):
        """
        Property: Generated URIs should be resolvable.
        Validates: Requirements 4B.1, 4B.2, 4B.3
        """
        assume(expert_id.strip())
        
        manager = ExpertResourceManager()
        manager.register_expert(
            expert_id=expert_id,
            name="Test",
            domain="Test",
            description="Test"
        )
        
        uri = manager.get_resource_uri(expert_id, resource_type)
        data = manager.resolve_uri(uri)
        
        assert data is not None
        assert data["expert_id"] == expert_id
    
    @given(st.lists(
        st.tuples(
            st.text(min_size=1, max_size=50),
            st.sampled_from(["low", "medium", "high"])
        ),
        min_size=0,
        max_size=20
    ))
    @settings(max_examples=30)
    def test_high_priority_count_accurate(self, gap_data: list[tuple[str, str]]):
        """
        Property: High priority count should match gaps with severity 'high'.
        """
        gaps = ExpertGaps(expert_id="test")
        
        for topic, severity in gap_data:
            gaps.add_gap(topic, severity)
        
        data = gaps.to_dict()
        expected_high = len([s for _, s in gap_data if s == "high"])
        
        assert data["high_priority_count"] == expected_high
        assert data["gap_count"] == len(gap_data)
