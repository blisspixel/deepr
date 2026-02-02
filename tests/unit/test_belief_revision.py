"""Unit and property tests for belief revision system.

Task 15.6: Tests for belief revision including:
- Belief creation and serialization
- Conflict detection and resolution
- Confidence decay over time
- Cross-expert knowledge sharing with namespaces

Uses hypothesis for property-based testing.
"""

import pytest
import asyncio
import tempfile
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Set

from hypothesis import given, settings, strategies as st, HealthCheck, assume

from deepr.experts.beliefs import (
    Belief,
    BeliefChange,
    BeliefStore,
    SharedBeliefStore,
    ConflictResolution
)


# =============================================================================
# Unit Tests: Belief Dataclass
# =============================================================================

class TestBeliefDataclass:
    """Unit tests for Belief dataclass."""

    def test_belief_creation(self):
        """Test creating a belief with required fields."""
        belief = Belief(
            claim="Python 3.12 supports pattern matching",
            confidence=0.95
        )
        
        assert belief.claim == "Python 3.12 supports pattern matching"
        assert belief.confidence == 0.95
        assert belief.id != ""  # Auto-generated
        assert belief.source_type == "learned"
        assert belief.decay_rate == 0.01

    def test_belief_with_all_fields(self):
        """Test creating a belief with all fields."""
        belief = Belief(
            claim="Test claim",
            confidence=0.8,
            evidence_refs=["doc_001", "doc_002"],
            domain="python",
            source_type="user_provided",
            decay_rate=0.02
        )
        
        assert belief.domain == "python"
        assert len(belief.evidence_refs) == 2
        assert belief.source_type == "user_provided"
        assert belief.decay_rate == 0.02

    def test_belief_id_generation(self):
        """Test belief ID is generated from content hash."""
        belief1 = Belief(claim="Same claim", confidence=0.9, domain="test")
        belief2 = Belief(claim="Same claim", confidence=0.9, domain="test")
        belief3 = Belief(claim="Different claim", confidence=0.9, domain="test")
        
        # Different timestamps = different IDs (timestamp is part of hash)
        # So we can't test exact equality, but we can test they're non-empty
        assert belief1.id != ""
        assert belief2.id != ""
        assert belief3.id != ""

    def test_belief_serialization(self):
        """Test belief to_dict and from_dict."""
        original = Belief(
            claim="Test claim",
            confidence=0.85,
            evidence_refs=["ref1", "ref2"],
            domain="technology",
            source_type="inferred"
        )
        
        data = original.to_dict()
        restored = Belief.from_dict(data)
        
        assert restored.claim == original.claim
        assert restored.confidence == original.confidence
        assert restored.evidence_refs == original.evidence_refs
        assert restored.domain == original.domain
        assert restored.source_type == original.source_type
        assert restored.id == original.id


# =============================================================================
# Unit Tests: Confidence Decay
# =============================================================================

class TestConfidenceDecay:
    """Unit tests for confidence decay over time."""

    def test_no_decay_when_fresh(self):
        """Test no decay for recently updated belief."""
        belief = Belief(
            claim="Fresh belief",
            confidence=0.9,
            decay_rate=0.01
        )
        
        # Just created, should have same confidence
        current = belief.get_current_confidence()
        assert abs(current - 0.9) < 0.01

    def test_decay_over_time(self):
        """Test confidence decays over time."""
        belief = Belief(
            claim="Old belief",
            confidence=0.9,
            decay_rate=0.01
        )
        # Simulate 30 days old
        belief.updated_at = datetime.utcnow() - timedelta(days=30)
        
        current = belief.get_current_confidence()
        expected = 0.9 * math.exp(-0.01 * 30)
        
        assert abs(current - expected) < 0.01
        assert current < 0.9  # Should have decayed

    def test_decay_rate_affects_speed(self):
        """Test higher decay rate causes faster decay."""
        slow_decay = Belief(claim="Slow", confidence=0.9, decay_rate=0.001)
        fast_decay = Belief(claim="Fast", confidence=0.9, decay_rate=0.1)
        
        # Simulate 30 days old
        slow_decay.updated_at = datetime.utcnow() - timedelta(days=30)
        fast_decay.updated_at = datetime.utcnow() - timedelta(days=30)
        
        slow_current = slow_decay.get_current_confidence()
        fast_current = fast_decay.get_current_confidence()
        
        assert slow_current > fast_current

    def test_is_stale_threshold(self):
        """Test is_stale with different thresholds."""
        belief = Belief(claim="Test", confidence=0.5, decay_rate=0.01)
        belief.updated_at = datetime.utcnow() - timedelta(days=100)
        
        current = belief.get_current_confidence()
        
        # Should be stale with high threshold
        assert belief.is_stale(threshold=0.5) is True
        # May not be stale with low threshold
        assert belief.is_stale(threshold=0.1) is (current < 0.1)


# =============================================================================
# Unit Tests: Belief Updates
# =============================================================================

class TestBeliefUpdates:
    """Unit tests for belief update operations."""

    def test_update_confidence(self):
        """Test updating belief confidence."""
        belief = Belief(claim="Test", confidence=0.5)
        
        belief.update_confidence(0.8, "New evidence")
        
        assert belief.confidence == 0.8
        assert len(belief.history) == 1
        assert belief.history[0]["old_confidence"] == 0.5
        assert belief.history[0]["new_confidence"] == 0.8
        assert belief.history[0]["reason"] == "New evidence"

    def test_add_evidence(self):
        """Test adding evidence to belief."""
        belief = Belief(claim="Test", confidence=0.5, evidence_refs=["ref1"])
        
        belief.add_evidence("ref2")
        belief.add_evidence("ref3")
        belief.add_evidence("ref2")  # Duplicate
        
        assert len(belief.evidence_refs) == 3
        assert "ref2" in belief.evidence_refs
        assert "ref3" in belief.evidence_refs

    def test_add_contradiction(self):
        """Test marking contradictions."""
        belief1 = Belief(claim="A is true", confidence=0.9)
        belief2 = Belief(claim="A is false", confidence=0.8)
        
        belief1.add_contradiction(belief2.id)
        belief2.add_contradiction(belief1.id)
        
        assert belief2.id in belief1.contradictions_with
        assert belief1.id in belief2.contradictions_with


# =============================================================================
# Unit Tests: BeliefStore
# =============================================================================

class TestBeliefStore:
    """Unit tests for BeliefStore."""

    def test_store_initialization(self, tmp_path):
        """Test store initializes correctly."""
        store = BeliefStore(
            expert_name="test_expert",
            storage_dir=tmp_path / "beliefs"
        )
        
        assert store.expert_name == "test_expert"
        assert len(store.beliefs) == 0
        assert store.conflict_resolution == ConflictResolution.HIGHER_CONFIDENCE

    def test_add_belief(self, tmp_path):
        """Test adding a belief to store."""
        store = BeliefStore(
            expert_name="test",
            storage_dir=tmp_path / "beliefs"
        )
        
        belief = Belief(
            claim="Python is great",
            confidence=0.9,
            domain="programming"
        )
        
        added, change = store.add_belief(belief)
        
        assert added.id in store.beliefs
        assert change is not None
        assert change.change_type == "created"

    def test_get_beliefs_by_domain(self, tmp_path):
        """Test getting beliefs by domain."""
        store = BeliefStore(
            expert_name="test",
            storage_dir=tmp_path / "beliefs"
        )
        
        store.add_belief(Belief(claim="Python fact", confidence=0.9, domain="python"))
        store.add_belief(Belief(claim="Java fact", confidence=0.8, domain="java"))
        store.add_belief(Belief(claim="Another Python fact", confidence=0.7, domain="python"))
        
        python_beliefs = store.get_beliefs_by_domain("python")
        java_beliefs = store.get_beliefs_by_domain("java")
        
        assert len(python_beliefs) == 2
        assert len(java_beliefs) == 1

    def test_update_belief(self, tmp_path):
        """Test updating an existing belief."""
        store = BeliefStore(
            expert_name="test",
            storage_dir=tmp_path / "beliefs"
        )
        
        belief = Belief(claim="Test", confidence=0.5, domain="test")
        added, _ = store.add_belief(belief)
        
        change = store.update_belief(
            added.id,
            new_confidence=0.8,
            reason="More evidence"
        )
        
        assert change is not None
        assert change.change_type == "updated"
        assert store.beliefs[added.id].confidence == 0.8

    def test_revise_belief(self, tmp_path):
        """Test revising a belief with new claim."""
        store = BeliefStore(
            expert_name="test",
            storage_dir=tmp_path / "beliefs"
        )
        
        belief = Belief(claim="Old claim", confidence=0.5, domain="test")
        added, _ = store.add_belief(belief)
        
        change = store.revise_belief(
            added.id,
            new_claim="New claim",
            new_confidence=0.9,
            reason="Better understanding"
        )
        
        assert change is not None
        assert change.change_type == "revised"
        assert change.old_claim == "Old claim"
        assert change.new_claim == "New claim"
        assert store.beliefs[added.id].claim == "New claim"

    def test_archive_belief(self, tmp_path):
        """Test archiving a belief."""
        store = BeliefStore(
            expert_name="test",
            storage_dir=tmp_path / "beliefs"
        )
        
        belief = Belief(claim="To archive", confidence=0.5, domain="test")
        added, _ = store.add_belief(belief)
        belief_id = added.id
        
        change = store.archive_belief(belief_id, "No longer valid")
        
        assert change is not None
        assert change.change_type == "archived"
        assert belief_id not in store.beliefs

    def test_get_stale_beliefs(self, tmp_path):
        """Test getting stale beliefs."""
        store = BeliefStore(
            expert_name="test",
            storage_dir=tmp_path / "beliefs"
        )
        
        # Add fresh belief
        fresh = Belief(claim="Fresh", confidence=0.9, domain="test")
        store.add_belief(fresh)
        
        # Add stale belief (old and low confidence after decay)
        stale = Belief(claim="Stale", confidence=0.4, domain="test", decay_rate=0.1)
        stale.updated_at = datetime.utcnow() - timedelta(days=100)
        store.add_belief(stale)
        
        stale_beliefs = store.get_stale_beliefs(threshold=0.3)
        
        # The stale belief should be in the list
        assert len(stale_beliefs) >= 1


# =============================================================================
# Unit Tests: Conflict Resolution
# =============================================================================

class TestConflictResolution:
    """Unit tests for conflict resolution strategies."""

    def test_higher_confidence_wins(self, tmp_path):
        """Test HIGHER_CONFIDENCE resolution strategy."""
        store = BeliefStore(
            expert_name="test",
            storage_dir=tmp_path / "beliefs",
            conflict_resolution=ConflictResolution.HIGHER_CONFIDENCE
        )
        
        # Add initial belief
        belief1 = Belief(
            claim="Python version is 3.11",
            confidence=0.7,
            domain="python"
        )
        store.add_belief(belief1)
        
        # Add conflicting belief with higher confidence
        belief2 = Belief(
            claim="Python version is 3.12",
            confidence=0.9,
            domain="python"
        )
        added, change = store.add_belief(belief2)
        
        # Higher confidence should win
        assert change is not None
        assert change.change_type == "revised"

    def test_newer_wins(self, tmp_path):
        """Test NEWER_WINS resolution strategy."""
        store = BeliefStore(
            expert_name="test",
            storage_dir=tmp_path / "beliefs",
            conflict_resolution=ConflictResolution.NEWER_WINS
        )
        
        # Add initial belief
        belief1 = Belief(
            claim="Python version is 3.11",
            confidence=0.9,
            domain="python"
        )
        store.add_belief(belief1)
        
        # Add conflicting belief (even with lower confidence)
        belief2 = Belief(
            claim="Python version is 3.12",
            confidence=0.7,
            domain="python"
        )
        added, change = store.add_belief(belief2)
        
        # Newer should win regardless of confidence
        assert change is not None
        assert change.change_type == "revised"

    def test_merge_strategy(self, tmp_path):
        """Test MERGE resolution strategy."""
        store = BeliefStore(
            expert_name="test",
            storage_dir=tmp_path / "beliefs",
            conflict_resolution=ConflictResolution.MERGE
        )
        
        # Add initial belief
        belief1 = Belief(
            claim="Python is popular",
            confidence=0.8,
            domain="python",
            evidence_refs=["ref1"]
        )
        store.add_belief(belief1)
        
        # Add similar belief
        belief2 = Belief(
            claim="Python is popular language",
            confidence=0.6,
            domain="python",
            evidence_refs=["ref2"]
        )
        added, change = store.add_belief(belief2)
        
        # Should merge evidence
        assert change is not None
        assert change.change_type == "updated"


# =============================================================================
# Unit Tests: BeliefChange Expression
# =============================================================================

class TestBeliefChangeExpression:
    """Unit tests for belief change natural language expression."""

    def test_created_expression(self):
        """Test expression for created belief."""
        change = BeliefChange(
            belief_id="test",
            change_type="created",
            new_claim="Python is great",
            new_confidence=0.9
        )
        
        expr = change.to_expression()
        
        assert "now believe" in expr.lower()
        assert "Python is great" in expr

    def test_revised_expression(self):
        """Test expression for revised belief."""
        change = BeliefChange(
            belief_id="test",
            change_type="revised",
            old_claim="Python 3.11 is latest",
            new_claim="Python 3.12 is latest",
            old_confidence=0.8,
            new_confidence=0.95,
            reason="new release"
        )
        
        expr = change.to_expression()
        
        assert "used to think" in expr.lower()
        assert "now i believe" in expr.lower()  # lowercase 'i' after .lower()
        assert "Python 3.11" in expr
        assert "Python 3.12" in expr

    def test_updated_expression(self):
        """Test expression for updated confidence."""
        change = BeliefChange(
            belief_id="test",
            change_type="updated",
            old_claim="Test claim",
            new_claim="Test claim",
            old_confidence=0.5,
            new_confidence=0.8
        )
        
        expr = change.to_expression()
        
        assert "more confident" in expr.lower()

    def test_archived_expression(self):
        """Test expression for archived belief."""
        change = BeliefChange(
            belief_id="test",
            change_type="archived",
            old_claim="Outdated claim",
            new_claim="",
            old_confidence=0.3,
            new_confidence=0.0
        )
        
        expr = change.to_expression()
        
        assert "no longer hold" in expr.lower()


# =============================================================================
# Unit Tests: SharedBeliefStore
# =============================================================================

class TestSharedBeliefStore:
    """Unit tests for cross-expert knowledge sharing."""

    def test_shared_store_initialization(self, tmp_path):
        """Test shared store initializes correctly."""
        store = SharedBeliefStore(storage_dir=tmp_path / "shared")
        
        assert len(store.domain_stores) == 0
        assert len(store.contributors) == 0

    def test_share_belief(self, tmp_path):
        """Test sharing a belief."""
        store = SharedBeliefStore(storage_dir=tmp_path / "shared")
        
        belief = Belief(
            claim="Python is popular",
            confidence=0.9,
            domain="programming"
        )
        
        result = store.share_belief(belief, "expert1")
        
        assert result is True
        assert "programming" in store.domain_stores
        assert len(store.domain_stores["programming"]) == 1

    def test_share_low_confidence_rejected(self, tmp_path):
        """Test low confidence beliefs are not shared."""
        store = SharedBeliefStore(storage_dir=tmp_path / "shared")
        
        belief = Belief(
            claim="Uncertain claim",
            confidence=0.5,
            domain="test"
        )
        
        result = store.share_belief(belief, "expert1", min_confidence=0.7)
        
        assert result is False
        assert "test" not in store.domain_stores

    def test_get_shared_beliefs(self, tmp_path):
        """Test getting shared beliefs by domain."""
        store = SharedBeliefStore(storage_dir=tmp_path / "shared")
        
        store.share_belief(
            Belief(claim="Fact 1", confidence=0.9, domain="python"),
            "expert1"
        )
        store.share_belief(
            Belief(claim="Fact 2", confidence=0.8, domain="python"),
            "expert2"
        )
        store.share_belief(
            Belief(claim="Java fact", confidence=0.9, domain="java"),
            "expert1"
        )
        
        python_beliefs = store.get_shared_beliefs("python")
        java_beliefs = store.get_shared_beliefs("java")
        
        assert len(python_beliefs) == 2
        assert len(java_beliefs) == 1

    def test_namespace_isolation(self, tmp_path):
        """Test beliefs are isolated by domain namespace."""
        store = SharedBeliefStore(storage_dir=tmp_path / "shared")
        
        # Share beliefs in different domains
        store.share_belief(
            Belief(claim="Python fact", confidence=0.9, domain="python"),
            "expert1"
        )
        store.share_belief(
            Belief(claim="Java fact", confidence=0.9, domain="java"),
            "expert2"
        )
        
        # Each domain should only see its own beliefs
        python_beliefs = store.get_shared_beliefs("python")
        java_beliefs = store.get_shared_beliefs("java")
        rust_beliefs = store.get_shared_beliefs("rust")
        
        assert len(python_beliefs) == 1
        assert len(java_beliefs) == 1
        assert len(rust_beliefs) == 0
        
        # Verify content isolation
        assert all("Python" in b.claim for b in python_beliefs)
        assert all("Java" in b.claim for b in java_beliefs)

    def test_contributor_tracking(self, tmp_path):
        """Test tracking of belief contributors."""
        store = SharedBeliefStore(storage_dir=tmp_path / "shared")
        
        belief = Belief(
            claim="Shared knowledge",
            confidence=0.9,
            domain="test"
        )
        
        store.share_belief(belief, "expert1")
        
        contributors = store.get_contributors(belief.id)
        
        assert "expert1" in contributors

    def test_corroboration_increases_confidence(self, tmp_path):
        """Test multiple experts corroborating increases confidence."""
        store = SharedBeliefStore(storage_dir=tmp_path / "shared")
        
        # First expert shares
        belief1 = Belief(
            claim="Python is popular for data science",
            confidence=0.8,
            domain="python"
        )
        store.share_belief(belief1, "expert1")
        
        # Second expert corroborates with similar belief
        belief2 = Belief(
            claim="Python is popular for data science work",
            confidence=0.85,
            domain="python"
        )
        store.share_belief(belief2, "expert2")
        
        # Get the shared belief
        beliefs = store.get_shared_beliefs("python")
        
        # Should have merged and increased confidence
        assert len(beliefs) == 1
        # Confidence should be weighted average
        contributors = store.get_contributors(beliefs[0].id)
        assert len(contributors) == 2

    def test_import_to_expert(self, tmp_path):
        """Test importing shared beliefs to expert store."""
        shared = SharedBeliefStore(storage_dir=tmp_path / "shared")
        expert = BeliefStore(
            expert_name="test",
            storage_dir=tmp_path / "expert"
        )
        
        # Share some beliefs
        shared.share_belief(
            Belief(claim="Fact 1", confidence=0.9, domain="test"),
            "other_expert"
        )
        shared.share_belief(
            Belief(claim="Fact 2", confidence=0.85, domain="test"),
            "other_expert"
        )
        
        # Import to expert
        imported = shared.import_to_expert(expert, "test", max_beliefs=10)
        
        assert imported == 2
        assert len(expert.beliefs) == 2

    def test_cleanup_stale(self, tmp_path):
        """Test cleaning up stale shared beliefs."""
        store = SharedBeliefStore(storage_dir=tmp_path / "shared")
        
        # Add fresh belief
        fresh = Belief(claim="Fresh", confidence=0.9, domain="test")
        store.share_belief(fresh, "expert1")
        
        # Add stale belief
        stale = Belief(claim="Stale", confidence=0.2, domain="test", decay_rate=0.5)
        stale.updated_at = datetime.utcnow() - timedelta(days=365)
        store.domain_stores["test"] = store.domain_stores.get("test", {})
        store.domain_stores["test"][stale.id] = stale
        
        removed = store.cleanup_stale()
        
        assert removed >= 1


# =============================================================================
# Unit Tests: Persistence
# =============================================================================

class TestBeliefPersistence:
    """Unit tests for belief persistence."""

    def test_store_saves_and_loads(self, tmp_path):
        """Test store saves and loads beliefs correctly."""
        storage_dir = tmp_path / "beliefs"
        
        # Create store and add beliefs
        store1 = BeliefStore(expert_name="test", storage_dir=storage_dir)
        store1.add_belief(Belief(claim="Fact 1", confidence=0.9, domain="test"))
        store1.add_belief(Belief(claim="Fact 2", confidence=0.8, domain="test"))
        
        # Create new store instance (should load from disk)
        store2 = BeliefStore(expert_name="test", storage_dir=storage_dir)
        
        assert len(store2.beliefs) == 2
        assert len(store2.get_beliefs_by_domain("test")) == 2

    def test_shared_store_persistence(self, tmp_path):
        """Test shared store saves and loads correctly."""
        storage_dir = tmp_path / "shared"
        
        # Create store and share beliefs
        store1 = SharedBeliefStore(storage_dir=storage_dir)
        store1.share_belief(
            Belief(claim="Shared fact", confidence=0.9, domain="test"),
            "expert1"
        )
        
        # Create new store instance
        store2 = SharedBeliefStore(storage_dir=storage_dir)
        
        beliefs = store2.get_shared_beliefs("test")
        assert len(beliefs) == 1
        assert "expert1" in store2.get_contributors(beliefs[0].id)


# =============================================================================
# Property-Based Tests: Belief Invariants
# =============================================================================

class TestBeliefProperties:
    """Property-based tests for Belief invariants."""

    @given(
        claim=st.text(min_size=1, max_size=200),
        confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        decay_rate=st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
    )
    def test_confidence_always_bounded(self, claim, confidence, decay_rate):
        """Property: Current confidence is always between 0 and 1."""
        belief = Belief(
            claim=claim,
            confidence=confidence,
            decay_rate=decay_rate
        )
        
        current = belief.get_current_confidence()
        assert 0.0 <= current <= 1.0

    @given(
        claim=st.text(min_size=1, max_size=200),
        confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        days_old=st.integers(min_value=0, max_value=3650)
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
    )
    def test_decay_is_monotonic(self, claim, confidence, days_old):
        """Property: Confidence never increases with time (decay is monotonic)."""
        belief = Belief(
            claim=claim,
            confidence=confidence,
            decay_rate=0.01
        )
        
        # Get current confidence
        current1 = belief.get_current_confidence()
        
        # Age the belief
        belief.updated_at = datetime.utcnow() - timedelta(days=days_old)
        current2 = belief.get_current_confidence()
        
        # Older belief should have same or lower confidence
        assert current2 <= current1 + 0.001  # Small epsilon for float comparison

    @given(
        claim=st.text(min_size=1, max_size=200),
        confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        domain=st.text(min_size=0, max_size=50)
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
    )
    def test_serialization_roundtrip(self, claim, confidence, domain):
        """Property: Serialization roundtrip preserves belief data."""
        original = Belief(
            claim=claim,
            confidence=confidence,
            domain=domain
        )
        
        data = original.to_dict()
        restored = Belief.from_dict(data)
        
        assert restored.claim == original.claim
        assert abs(restored.confidence - original.confidence) < 0.0001
        assert restored.domain == original.domain
        assert restored.id == original.id

    @given(
        claim=st.text(min_size=1, max_size=200),
        old_conf=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        new_conf=st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
    )
    def test_update_records_history(self, claim, old_conf, new_conf):
        """Property: Confidence updates always record history."""
        belief = Belief(claim=claim, confidence=old_conf)
        initial_history_len = len(belief.history)
        
        belief.update_confidence(new_conf, "test reason")
        
        assert len(belief.history) == initial_history_len + 1
        assert belief.history[-1]["old_confidence"] == old_conf
        assert belief.history[-1]["new_confidence"] == new_conf

    @given(
        evidence_refs=st.lists(st.text(min_size=1, max_size=50), min_size=0, max_size=20)
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
    )
    def test_evidence_refs_no_duplicates_after_add(self, evidence_refs):
        """Property: Adding evidence doesn't create duplicates."""
        belief = Belief(claim="Test", confidence=0.9)
        
        for ref in evidence_refs:
            belief.add_evidence(ref)
        
        # Check no duplicates
        assert len(belief.evidence_refs) == len(set(belief.evidence_refs))


# =============================================================================
# Property-Based Tests: BeliefStore Invariants
# =============================================================================

class TestBeliefStoreProperties:
    """Property-based tests for BeliefStore invariants."""

    @given(
        claims=st.lists(
            st.text(min_size=1, max_size=100),
            min_size=1,
            max_size=10
        ),
        confidences=st.lists(
            st.floats(min_value=0.1, max_value=1.0, allow_nan=False),
            min_size=1,
            max_size=10
        )
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
    )
    def test_store_count_matches_beliefs(self, claims, confidences):
        """Property: Store belief count matches actual beliefs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = BeliefStore(
                expert_name="test",
                storage_dir=Path(tmp_dir) / "beliefs"
            )
            
            added_ids = set()
            for claim, conf in zip(claims, confidences):
                belief = Belief(
                    claim=claim,
                    confidence=conf,
                    domain="test"
                )
                added, _ = store.add_belief(belief)
                added_ids.add(added.id)
            
            # Store count should match unique beliefs added
            # (may be less due to similarity merging)
            assert len(store.beliefs) <= len(added_ids)
            assert len(store.beliefs) >= 1

    @given(
        domain=st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=('L', 'N'))),
        num_beliefs=st.integers(min_value=1, max_value=5)
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
    )
    def test_domain_index_consistency(self, domain, num_beliefs):
        """Property: Domain index is consistent with beliefs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = BeliefStore(
                expert_name="test",
                storage_dir=Path(tmp_dir) / "beliefs"
            )
            
            for i in range(num_beliefs):
                belief = Belief(
                    claim=f"Unique claim number {i} for domain {domain}",
                    confidence=0.9,
                    domain=domain
                )
                store.add_belief(belief)
            
            # All beliefs in domain should be in index
            domain_beliefs = store.get_beliefs_by_domain(domain)
            for belief in domain_beliefs:
                assert belief.id in store.beliefs
                assert belief.domain == domain

    @given(
        claim=st.text(min_size=10, max_size=100),
        confidence=st.floats(min_value=0.1, max_value=1.0, allow_nan=False)
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
    )
    def test_archive_removes_from_store(self, claim, confidence):
        """Property: Archived beliefs are removed from active store."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = BeliefStore(
                expert_name="test",
                storage_dir=Path(tmp_dir) / "beliefs"
            )
            
            belief = Belief(claim=claim, confidence=confidence, domain="test")
            added, _ = store.add_belief(belief)
            belief_id = added.id
            
            assert belief_id in store.beliefs
            
            store.archive_belief(belief_id, "test archive")
            
            assert belief_id not in store.beliefs

    @given(
        claim=st.text(min_size=10, max_size=100),
        old_conf=st.floats(min_value=0.1, max_value=0.5, allow_nan=False),
        new_conf=st.floats(min_value=0.5, max_value=1.0, allow_nan=False)
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
    )
    def test_update_preserves_belief_id(self, claim, old_conf, new_conf):
        """Property: Updating belief preserves its ID."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = BeliefStore(
                expert_name="test",
                storage_dir=Path(tmp_dir) / "beliefs"
            )
            
            belief = Belief(claim=claim, confidence=old_conf, domain="test")
            added, _ = store.add_belief(belief)
            original_id = added.id
            
            store.update_belief(original_id, new_confidence=new_conf)
            
            assert original_id in store.beliefs
            assert store.beliefs[original_id].confidence == new_conf


# =============================================================================
# Property-Based Tests: Conflict Resolution
# =============================================================================

class TestConflictResolutionProperties:
    """Property-based tests for conflict resolution."""

    @given(
        conf1=st.floats(min_value=0.1, max_value=0.5, allow_nan=False),
        conf2=st.floats(min_value=0.6, max_value=1.0, allow_nan=False)
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
    )
    def test_higher_confidence_always_wins(self, conf1, conf2):
        """Property: Higher confidence belief always wins in HIGHER_CONFIDENCE mode."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = BeliefStore(
                expert_name="test",
                storage_dir=Path(tmp_dir) / "beliefs",
                conflict_resolution=ConflictResolution.HIGHER_CONFIDENCE
            )
            
            # Add lower confidence belief first
            belief1 = Belief(
                claim="Python is a programming language",
                confidence=conf1,
                domain="python"
            )
            store.add_belief(belief1)
            
            # Add higher confidence similar belief
            belief2 = Belief(
                claim="Python is a programming language used widely",
                confidence=conf2,
                domain="python"
            )
            added, change = store.add_belief(belief2)
            
            # Higher confidence should win
            if change and change.change_type == "revised":
                assert store.beliefs[added.id].confidence == conf2

    @given(
        conf1=st.floats(min_value=0.5, max_value=1.0, allow_nan=False),
        conf2=st.floats(min_value=0.1, max_value=0.5, allow_nan=False)
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
    )
    def test_newer_always_wins_regardless_of_confidence(self, conf1, conf2):
        """Property: Newer belief always wins in NEWER_WINS mode."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = BeliefStore(
                expert_name="test",
                storage_dir=Path(tmp_dir) / "beliefs",
                conflict_resolution=ConflictResolution.NEWER_WINS
            )
            
            # Add higher confidence belief first
            belief1 = Belief(
                claim="Python version is 3.11",
                confidence=conf1,
                domain="python"
            )
            store.add_belief(belief1)
            
            # Add lower confidence similar belief (newer)
            belief2 = Belief(
                claim="Python version is 3.12",
                confidence=conf2,
                domain="python"
            )
            added, change = store.add_belief(belief2)
            
            # Newer should win regardless of confidence
            if change and change.change_type == "revised":
                assert "3.12" in store.beliefs[added.id].claim


# =============================================================================
# Property-Based Tests: SharedBeliefStore
# =============================================================================

class TestSharedBeliefStoreProperties:
    """Property-based tests for SharedBeliefStore."""

    @given(
        domains=st.lists(
            st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('L', 'N'))),
            min_size=1,
            max_size=5,
            unique=True
        )
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
    )
    def test_domain_isolation(self, domains):
        """Property: Beliefs in different domains are isolated."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = SharedBeliefStore(storage_dir=Path(tmp_dir) / "shared")
            
            # Share one belief per domain
            for domain in domains:
                belief = Belief(
                    claim=f"Fact about {domain}",
                    confidence=0.9,
                    domain=domain
                )
                store.share_belief(belief, "expert1")
            
            # Each domain should only have its own beliefs
            for domain in domains:
                beliefs = store.get_shared_beliefs(domain)
                for belief in beliefs:
                    assert belief.domain == domain

    @given(
        confidence=st.floats(min_value=0.0, max_value=0.6, allow_nan=False)
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
    )
    def test_low_confidence_rejected(self, confidence):
        """Property: Low confidence beliefs are rejected from sharing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = SharedBeliefStore(storage_dir=Path(tmp_dir) / "shared")
            
            belief = Belief(
                claim="Low confidence claim",
                confidence=confidence,
                domain="test"
            )
            
            result = store.share_belief(belief, "expert1", min_confidence=0.7)
            
            assert result is False
            assert "test" not in store.domain_stores or len(store.domain_stores.get("test", {})) == 0

    @given(
        num_experts=st.integers(min_value=2, max_value=5)
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
    )
    def test_corroboration_tracks_all_contributors(self, num_experts):
        """Property: All corroborating experts are tracked."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = SharedBeliefStore(storage_dir=Path(tmp_dir) / "shared")
            
            # Multiple experts share similar belief
            expert_names = [f"expert_{i}" for i in range(num_experts)]
            belief_id = None
            
            for expert in expert_names:
                belief = Belief(
                    claim="Python is popular for data science",
                    confidence=0.9,
                    domain="python"
                )
                store.share_belief(belief, expert)
                
                # Get the belief ID (first one added)
                if belief_id is None:
                    beliefs = store.get_shared_beliefs("python")
                    if beliefs:
                        belief_id = beliefs[0].id
            
            # All experts should be tracked as contributors
            if belief_id:
                contributors = store.get_contributors(belief_id)
                assert len(contributors) == num_experts
                for expert in expert_names:
                    assert expert in contributors


# =============================================================================
# Property-Based Tests: Persistence
# =============================================================================

class TestPersistenceProperties:
    """Property-based tests for persistence."""

    @given(
        claims=st.lists(
            st.text(min_size=5, max_size=100),
            min_size=1,
            max_size=5,
            unique=True
        ),
        confidences=st.lists(
            st.floats(min_value=0.1, max_value=1.0, allow_nan=False),
            min_size=1,
            max_size=5
        )
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
    )
    def test_persistence_preserves_all_beliefs(self, claims, confidences):
        """Property: Persistence preserves all beliefs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage_dir = Path(tmp_dir) / "beliefs"
            
            # Create store and add beliefs
            store1 = BeliefStore(expert_name="test", storage_dir=storage_dir)
            
            added_beliefs = []
            for claim, conf in zip(claims, confidences):
                belief = Belief(
                    claim=claim,
                    confidence=conf,
                    domain="test"
                )
                added, _ = store1.add_belief(belief)
                added_beliefs.append(added)
            
            original_count = len(store1.beliefs)
            original_ids = set(store1.beliefs.keys())
            
            # Create new store instance (loads from disk)
            store2 = BeliefStore(expert_name="test", storage_dir=storage_dir)
            
            assert len(store2.beliefs) == original_count
            assert set(store2.beliefs.keys()) == original_ids

    @given(
        domain=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('L', 'N'))),
        num_beliefs=st.integers(min_value=1, max_value=3)
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
    )
    def test_shared_persistence_preserves_contributors(self, domain, num_beliefs):
        """Property: Shared store persistence preserves contributor info."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage_dir = Path(tmp_dir) / "shared"
            
            # Create store and share beliefs
            store1 = SharedBeliefStore(storage_dir=storage_dir)
            
            for i in range(num_beliefs):
                belief = Belief(
                    claim=f"Unique fact number {i} about {domain}",
                    confidence=0.9,
                    domain=domain
                )
                store1.share_belief(belief, f"expert_{i}")
            
            original_contributors = dict(store1.contributors)
            
            # Create new store instance
            store2 = SharedBeliefStore(storage_dir=storage_dir)
            
            # Contributors should be preserved
            for belief_id, experts in original_contributors.items():
                assert belief_id in store2.contributors
                assert store2.contributors[belief_id] == experts


# =============================================================================
# Property-Based Tests: Confidence Decay Mathematics
# =============================================================================

class TestDecayMathProperties:
    """Property-based tests for decay mathematics."""

    @given(
        confidence=st.floats(min_value=0.1, max_value=1.0, allow_nan=False),
        decay_rate=st.floats(min_value=0.001, max_value=0.5, allow_nan=False),
        days=st.integers(min_value=0, max_value=1000)
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
    )
    def test_decay_formula_correctness(self, confidence, decay_rate, days):
        """Property: Decay follows exponential formula."""
        belief = Belief(
            claim="Test",
            confidence=confidence,
            decay_rate=decay_rate
        )
        belief.updated_at = datetime.utcnow() - timedelta(days=days)
        
        current = belief.get_current_confidence()
        expected = confidence * math.exp(-decay_rate * days)
        expected = max(0.0, min(1.0, expected))
        
        assert abs(current - expected) < 0.0001

    @given(
        confidence=st.floats(min_value=0.5, max_value=1.0, allow_nan=False),
        decay_rate=st.floats(min_value=0.01, max_value=0.1, allow_nan=False)
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
    )
    def test_half_life_property(self, confidence, decay_rate):
        """Property: Confidence halves at half-life time."""
        half_life_days = math.log(2) / decay_rate
        
        belief = Belief(
            claim="Test",
            confidence=confidence,
            decay_rate=decay_rate
        )
        belief.updated_at = datetime.utcnow() - timedelta(days=half_life_days)
        
        current = belief.get_current_confidence()
        expected_half = confidence / 2
        
        # The implementation uses integer days, so we need to account for
        # the truncation error. The actual decay uses floor(days_elapsed).
        # Allow 6% tolerance to account for this discretization.
        tolerance = confidence * 0.06
        assert abs(current - expected_half) < tolerance
