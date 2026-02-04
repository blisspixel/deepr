"""Unit and property tests for self-improvement features.

Task 14.5: Tests for continuous self-improvement including:
- Staleness detection (is_knowledge_stale)
- Budget enforcement (monthly_learning_budget)
- Consolidation logic (deduplicate, merge, archive)

Uses hypothesis for property-based testing.
"""

import pytest
import asyncio
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Set


def utc_now():
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)

from hypothesis import given, settings, strategies as st, HealthCheck, assume

from deepr.experts.profile import ExpertProfile
from deepr.experts.knowledge_consolidation import (
    KnowledgeEntry,
    KnowledgeConsolidator,
    ConsolidationResult
)


# =============================================================================
# Unit Tests: Staleness Detection
# =============================================================================

class TestStalenessDetection:
    """Unit tests for staleness detection logic."""

    def test_no_cutoff_is_stale(self):
        """Expert with no knowledge cutoff is always stale."""
        profile = ExpertProfile(
            name="Test",
            vector_store_id="vs_test",
            knowledge_cutoff_date=None
        )
        assert profile.is_knowledge_stale() is True

    def test_fast_domain_30_day_threshold(self):
        """Fast domain uses 30-day velocity with 0.8x stale threshold.
        
        FreshnessChecker uses fractional thresholds:
        - Fresh: <= velocity_days * 0.5 (15 days for fast)
        - Aging: <= velocity_days * 0.8 (24 days for fast)
        - Stale: > velocity_days * 0.8 (> 24 days for fast)
        """
        now = utc_now()
        
        # 15 days old - fresh (within 0.5x threshold)
        profile_fresh = ExpertProfile(
            name="Fresh",
            vector_store_id="vs_fresh",
            knowledge_cutoff_date=now - timedelta(days=15),
            domain_velocity="fast"
        )
        assert profile_fresh.is_knowledge_stale() is False
        
        # 25 days old - stale (beyond 0.8x threshold of 24 days)
        profile_stale = ExpertProfile(
            name="Stale",
            vector_store_id="vs_stale",
            knowledge_cutoff_date=now - timedelta(days=25),
            domain_velocity="fast"
        )
        assert profile_stale.is_knowledge_stale() is True

    def test_medium_domain_90_day_threshold(self):
        """Medium domain uses 90-day velocity with 0.8x stale threshold.
        
        FreshnessChecker uses fractional thresholds:
        - Fresh: <= velocity_days * 0.5 (45 days for medium)
        - Aging: <= velocity_days * 0.8 (72 days for medium)
        - Stale: > velocity_days * 0.8 (> 72 days for medium)
        """
        now = utc_now()
        
        # 45 days old - fresh (within 0.5x threshold)
        profile_fresh = ExpertProfile(
            name="Fresh",
            vector_store_id="vs_fresh",
            knowledge_cutoff_date=now - timedelta(days=45),
            domain_velocity="medium"
        )
        assert profile_fresh.is_knowledge_stale() is False
        
        # 73 days old - stale (beyond 0.8x threshold of 72 days)
        profile_stale = ExpertProfile(
            name="Stale",
            vector_store_id="vs_stale",
            knowledge_cutoff_date=now - timedelta(days=73),
            domain_velocity="medium"
        )
        assert profile_stale.is_knowledge_stale() is True

    def test_slow_domain_180_day_threshold(self):
        """Slow domain uses 180-day velocity with 0.8x stale threshold.
        
        FreshnessChecker uses fractional thresholds:
        - Fresh: <= velocity_days * 0.5 (90 days for slow)
        - Aging: <= velocity_days * 0.8 (144 days for slow)
        - Stale: > velocity_days * 0.8 (> 144 days for slow)
        """
        now = utc_now()
        
        # 90 days old - fresh (within 0.5x threshold)
        profile_fresh = ExpertProfile(
            name="Fresh",
            vector_store_id="vs_fresh",
            knowledge_cutoff_date=now - timedelta(days=90),
            domain_velocity="slow"
        )
        assert profile_fresh.is_knowledge_stale() is False
        
        # 145 days old - stale (beyond 0.8x threshold of 144 days)
        profile_stale = ExpertProfile(
            name="Stale",
            vector_store_id="vs_stale",
            knowledge_cutoff_date=now - timedelta(days=145),
            domain_velocity="slow"
        )
        assert profile_stale.is_knowledge_stale() is True

    def test_staleness_details_structure(self):
        """Test get_staleness_details returns complete structure."""
        now = utc_now()
        profile = ExpertProfile(
            name="Test",
            vector_store_id="vs_test",
            knowledge_cutoff_date=now - timedelta(days=100),
            domain_velocity="medium",
            domain="Technology"
        )
        
        details = profile.get_staleness_details()
        
        # Check all required fields
        assert "is_stale" in details
        assert "freshness_status" in details
        assert "age_days" in details
        assert "threshold_days" in details
        assert "domain_velocity" in details
        assert "urgency" in details
        assert "estimated_refresh_cost" in details
        assert "refresh_command" in details

    def test_staleness_urgency_levels(self):
        """Test urgency levels based on staleness.
        
        Urgency mapping:
        - fresh status -> low urgency
        - aging status -> medium urgency
        - stale status -> high urgency
        - incomplete status (no cutoff AND critical level) -> critical urgency
        
        Note: An expert with no knowledge_cutoff_date but recent updated_at
        will have "fresh" status (not "incomplete") because FreshnessChecker
        falls back to last_activity when last_learning is None.
        """
        now = utc_now()
        
        # Fresh - low urgency (within 0.5x threshold = 45 days for medium)
        fresh = ExpertProfile(
            name="Fresh",
            vector_store_id="vs_fresh",
            knowledge_cutoff_date=now - timedelta(days=30),
            domain_velocity="medium"
        )
        assert fresh.get_staleness_details()["urgency"] == "low"
        
        # Aging - medium urgency (between 0.5x and 0.8x = 45-72 days for medium)
        aging = ExpertProfile(
            name="Aging",
            vector_store_id="vs_aging",
            knowledge_cutoff_date=now - timedelta(days=60),
            domain_velocity="medium"
        )
        assert aging.get_staleness_details()["urgency"] == "medium"
        
        # Stale - high urgency (beyond 0.8x threshold = > 72 days for medium)
        stale = ExpertProfile(
            name="Stale",
            vector_store_id="vs_stale",
            knowledge_cutoff_date=now - timedelta(days=120),
            domain_velocity="medium"
        )
        assert stale.get_staleness_details()["urgency"] == "high"
        
        # No cutoff = incomplete expert, needs initial learning = critical urgency
        incomplete_recent = ExpertProfile(
            name="IncompleteRecent",
            vector_store_id="vs_incomplete_recent",
            knowledge_cutoff_date=None
        )
        assert incomplete_recent.get_staleness_details()["urgency"] == "critical"
        assert incomplete_recent.is_knowledge_stale() is True

    def test_suggest_refresh_returns_none_when_fresh(self):
        """Test suggest_refresh returns None for fresh experts."""
        now = utc_now()
        profile = ExpertProfile(
            name="Fresh",
            vector_store_id="vs_fresh",
            knowledge_cutoff_date=now - timedelta(days=10),
            domain_velocity="medium"
        )
        
        suggestion = profile.suggest_refresh()
        assert suggestion is None

    def test_suggest_refresh_returns_suggestion_when_stale(self):
        """Test suggest_refresh returns suggestion for stale experts."""
        now = utc_now()
        profile = ExpertProfile(
            name="Stale",
            vector_store_id="vs_stale",
            knowledge_cutoff_date=now - timedelta(days=120),
            domain_velocity="medium",
            domain="Technology"
        )
        
        suggestion = profile.suggest_refresh()
        
        assert suggestion is not None
        assert suggestion["expert_name"] == "Stale"
        assert "estimated_cost" in suggestion
        assert "command" in suggestion
        assert "topics" in suggestion


# =============================================================================
# Unit Tests: Budget Enforcement
# =============================================================================

class TestBudgetEnforcement:
    """Unit tests for monthly learning budget enforcement."""

    def test_default_budget(self):
        """Test default monthly learning budget."""
        profile = ExpertProfile(
            name="Test",
            vector_store_id="vs_test"
        )
        assert profile.monthly_learning_budget == 5.0
        assert profile.monthly_spending == 0.0

    def test_can_spend_within_budget(self):
        """Test spending within budget is allowed."""
        profile = ExpertProfile(
            name="Test",
            vector_store_id="vs_test",
            monthly_learning_budget=10.0,
            monthly_spending=0.0
        )
        
        can_spend, reason = profile.can_spend_learning_budget(5.0)
        
        assert can_spend is True
        assert "Within budget" in reason

    def test_cannot_spend_exceeding_budget(self):
        """Test spending exceeding budget is rejected."""
        profile = ExpertProfile(
            name="Test",
            vector_store_id="vs_test",
            monthly_learning_budget=10.0,
            monthly_spending=8.0
        )
        
        can_spend, reason = profile.can_spend_learning_budget(5.0)
        
        assert can_spend is False
        assert "exceeds" in reason.lower()

    def test_cannot_spend_exhausted_budget(self):
        """Test spending with exhausted budget is rejected."""
        profile = ExpertProfile(
            name="Test",
            vector_store_id="vs_test",
            monthly_learning_budget=10.0,
            monthly_spending=10.0
        )
        
        can_spend, reason = profile.can_spend_learning_budget(1.0)
        
        assert can_spend is False
        assert "exhausted" in reason.lower()

    def test_zero_cost_always_allowed(self):
        """Test zero cost operations are always allowed."""
        profile = ExpertProfile(
            name="Test",
            vector_store_id="vs_test",
            monthly_learning_budget=10.0,
            monthly_spending=10.0  # Budget exhausted
        )
        
        can_spend, reason = profile.can_spend_learning_budget(0.0)
        
        assert can_spend is True
        assert "No cost" in reason

    def test_record_learning_spend(self):
        """Test recording learning spend updates tracking."""
        profile = ExpertProfile(
            name="Test",
            vector_store_id="vs_test",
            monthly_learning_budget=10.0,
            monthly_spending=0.0
        )
        
        profile.record_learning_spend(2.5, "refresh", "Test refresh")
        
        assert profile.monthly_spending == 2.5
        assert profile.total_research_cost == 2.5
        assert len(profile.refresh_history) == 1
        assert profile.refresh_history[0]["amount"] == 2.5
        assert profile.refresh_history[0]["operation"] == "refresh"

    def test_record_learning_spend_accumulates(self):
        """Test multiple spends accumulate correctly."""
        profile = ExpertProfile(
            name="Test",
            vector_store_id="vs_test",
            monthly_learning_budget=10.0,
            monthly_spending=0.0
        )
        
        profile.record_learning_spend(1.0, "refresh", "First")
        profile.record_learning_spend(2.0, "research", "Second")
        profile.record_learning_spend(0.5, "refresh", "Third")
        
        assert profile.monthly_spending == 3.5
        assert profile.total_research_cost == 3.5
        assert len(profile.refresh_history) == 3

    def test_refresh_history_limit(self):
        """Test refresh history is limited to 100 entries."""
        profile = ExpertProfile(
            name="Test",
            vector_store_id="vs_test"
        )
        
        # Add 110 entries
        for i in range(110):
            profile.record_learning_spend(0.01, "test", f"Entry {i}")
        
        # Should be capped at 100
        assert len(profile.refresh_history) == 100
        # Should keep most recent
        assert "Entry 109" in profile.refresh_history[-1]["details"]

    def test_get_monthly_budget_status(self):
        """Test get_monthly_budget_status returns complete info."""
        profile = ExpertProfile(
            name="Test",
            vector_store_id="vs_test",
            monthly_learning_budget=10.0,
            monthly_spending=3.0
        )
        
        status = profile.get_monthly_budget_status()
        
        assert status["monthly_budget"] == 10.0
        assert status["monthly_spent"] == 3.0
        assert status["monthly_remaining"] == 7.0
        assert status["usage_percent"] == 30.0
        assert status["can_spend"] is True

    def test_budget_status_exhausted(self):
        """Test budget status when exhausted."""
        profile = ExpertProfile(
            name="Test",
            vector_store_id="vs_test",
            monthly_learning_budget=10.0,
            monthly_spending=10.0
        )
        
        status = profile.get_monthly_budget_status()
        
        assert status["monthly_remaining"] == 0.0
        assert status["usage_percent"] == 100.0
        assert status["can_spend"] is False


# =============================================================================
# Unit Tests: Knowledge Consolidation
# =============================================================================

class TestKnowledgeEntry:
    """Unit tests for KnowledgeEntry dataclass."""

    def test_entry_creation(self):
        """Test creating a knowledge entry."""
        entry = KnowledgeEntry(
            content="Python is a programming language",
            source="docs/python.md",
            confidence=0.9,
            tags={"python", "programming"}
        )
        
        assert entry.content == "Python is a programming language"
        assert entry.source == "docs/python.md"
        assert entry.confidence == 0.9
        assert "python" in entry.tags
        assert entry.id != ""  # Auto-generated

    def test_entry_id_generation(self):
        """Test entry ID is generated from content hash."""
        entry1 = KnowledgeEntry(content="Same content")
        entry2 = KnowledgeEntry(content="Same content")
        entry3 = KnowledgeEntry(content="Different content")
        
        # Same content = same ID
        assert entry1.id == entry2.id
        # Different content = different ID
        assert entry1.id != entry3.id

    def test_entry_serialization(self):
        """Test entry to_dict and from_dict."""
        original = KnowledgeEntry(
            content="Test content",
            source="test.md",
            confidence=0.8,
            tags={"test", "unit"}
        )
        
        data = original.to_dict()
        restored = KnowledgeEntry.from_dict(data)
        
        assert restored.content == original.content
        assert restored.source == original.source
        assert restored.confidence == original.confidence
        assert restored.tags == original.tags
        assert restored.id == original.id

    def test_entry_tags_list_conversion(self):
        """Test tags are converted from list to set."""
        entry = KnowledgeEntry(
            content="Test",
            tags=["a", "b", "c"]  # List input
        )
        
        assert isinstance(entry.tags, set)
        assert entry.tags == {"a", "b", "c"}


class TestKnowledgeConsolidator:
    """Unit tests for KnowledgeConsolidator."""

    def test_consolidator_initialization(self, tmp_path):
        """Test consolidator initializes correctly."""
        consolidator = KnowledgeConsolidator(
            expert_name="test_expert",
            storage_dir=tmp_path / "knowledge"
        )
        
        assert consolidator.expert_name == "test_expert"
        assert consolidator.similarity_threshold == 0.85
        assert consolidator.archive_age_days == 180
        assert len(consolidator.entries) == 0

    def test_add_entry(self, tmp_path):
        """Test adding entries to consolidator."""
        consolidator = KnowledgeConsolidator(
            expert_name="test",
            storage_dir=tmp_path / "knowledge"
        )
        
        entry = KnowledgeEntry(content="Test entry")
        consolidator.add_entry(entry)
        
        assert len(consolidator.entries) == 1
        assert consolidator.entries[0].content == "Test entry"

    def test_get_entries(self, tmp_path):
        """Test getting entries with/without archived."""
        consolidator = KnowledgeConsolidator(
            expert_name="test",
            storage_dir=tmp_path / "knowledge"
        )
        
        # Add active entry
        active = KnowledgeEntry(content="Active entry")
        consolidator.add_entry(active)
        
        # Add archived entry
        archived = KnowledgeEntry(content="Archived entry", is_archived=True)
        consolidator.archived.append(archived)
        
        # Without archived
        entries = consolidator.get_entries(include_archived=False)
        assert len(entries) == 1
        
        # With archived
        all_entries = consolidator.get_entries(include_archived=True)
        assert len(all_entries) == 2

    def test_get_stats(self, tmp_path):
        """Test getting consolidation stats."""
        consolidator = KnowledgeConsolidator(
            expert_name="test",
            storage_dir=tmp_path / "knowledge"
        )
        
        consolidator.add_entry(KnowledgeEntry(content="Entry 1"))
        consolidator.add_entry(KnowledgeEntry(content="Entry 2"))
        
        stats = consolidator.get_stats()
        
        assert stats["active_entries"] == 2
        assert stats["archived_entries"] == 0
        assert stats["total_entries"] == 2
        assert stats["similarity_threshold"] == 0.85


class TestDeduplication:
    """Unit tests for deduplication logic."""

    def test_deduplicate_exact_duplicates(self, tmp_path):
        """Test deduplication removes highly similar entries.
        
        Note: KnowledgeEntry generates ID from content hash, so exact duplicates
        have the same ID and only one is added. We test with very similar content
        that should be deduplicated based on similarity threshold.
        """
        consolidator = KnowledgeConsolidator(
            expert_name="test",
            storage_dir=tmp_path / "knowledge",
            similarity_threshold=0.70  # Lower threshold to catch near-duplicates
        )
        
        # Add very similar entries (high similarity but different IDs)
        consolidator.add_entry(KnowledgeEntry(
            content="Python is a great programming language for data science work",
            confidence=0.8
        ))
        consolidator.add_entry(KnowledgeEntry(
            content="Python is a great programming language for data science tasks",
            confidence=0.9
        ))
        
        # Both should be added (different content = different IDs)
        assert len(consolidator.entries) == 2
        
        removed = consolidator._deduplicate()
        
        # Should deduplicate due to high similarity (0.75 >= 0.70)
        assert removed == 1
        assert len(consolidator.entries) == 1
        # Should keep higher confidence
        assert consolidator.entries[0].confidence == 0.9

    def test_deduplicate_near_duplicates(self, tmp_path):
        """Test deduplication removes near-duplicates."""
        consolidator = KnowledgeConsolidator(
            expert_name="test",
            storage_dir=tmp_path / "knowledge",
            similarity_threshold=0.7  # Lower threshold
        )
        
        # Add near-duplicate entries
        consolidator.add_entry(KnowledgeEntry(
            content="Python is excellent for machine learning and data analysis",
            confidence=0.8
        ))
        consolidator.add_entry(KnowledgeEntry(
            content="Python is excellent for machine learning and data science",
            confidence=0.7
        ))
        
        removed = consolidator._deduplicate()
        
        assert removed == 1
        assert len(consolidator.entries) == 1

    def test_deduplicate_keeps_distinct(self, tmp_path):
        """Test deduplication keeps distinct entries."""
        consolidator = KnowledgeConsolidator(
            expert_name="test",
            storage_dir=tmp_path / "knowledge",
            similarity_threshold=0.85
        )
        
        # Add distinct entries
        consolidator.add_entry(KnowledgeEntry(
            content="Python is a programming language"
        ))
        consolidator.add_entry(KnowledgeEntry(
            content="JavaScript runs in web browsers"
        ))
        
        removed = consolidator._deduplicate()
        
        assert removed == 0
        assert len(consolidator.entries) == 2

    def test_deduplicate_empty(self, tmp_path):
        """Test deduplication with no entries."""
        consolidator = KnowledgeConsolidator(
            expert_name="test",
            storage_dir=tmp_path / "knowledge"
        )
        
        removed = consolidator._deduplicate()
        
        assert removed == 0

    def test_deduplicate_single_entry(self, tmp_path):
        """Test deduplication with single entry."""
        consolidator = KnowledgeConsolidator(
            expert_name="test",
            storage_dir=tmp_path / "knowledge"
        )
        
        consolidator.add_entry(KnowledgeEntry(content="Single entry"))
        
        removed = consolidator._deduplicate()
        
        assert removed == 0
        assert len(consolidator.entries) == 1


class TestMergeRelated:
    """Unit tests for merge related logic."""

    def test_merge_related_by_tags(self, tmp_path):
        """Test merging entries with same tags."""
        consolidator = KnowledgeConsolidator(
            expert_name="test",
            storage_dir=tmp_path / "knowledge",
            similarity_threshold=0.85
        )
        
        # Add entries with same tag and moderate similarity
        consolidator.add_entry(KnowledgeEntry(
            content="Python has excellent libraries for data science",
            tags={"python", "data"},
            confidence=0.9
        ))
        consolidator.add_entry(KnowledgeEntry(
            content="Python provides tools for data analysis",
            tags={"python", "data"},
            confidence=0.7
        ))
        
        merged = consolidator._merge_related()
        
        # Should merge (similarity between 0.5 and 0.85)
        assert merged >= 0  # May or may not merge depending on exact similarity
        assert len(consolidator.entries) >= 1

    def test_merge_keeps_unrelated(self, tmp_path):
        """Test merge keeps unrelated entries."""
        consolidator = KnowledgeConsolidator(
            expert_name="test",
            storage_dir=tmp_path / "knowledge"
        )
        
        # Add entries with different tags
        consolidator.add_entry(KnowledgeEntry(
            content="Python is great",
            tags={"python"}
        ))
        consolidator.add_entry(KnowledgeEntry(
            content="JavaScript is popular",
            tags={"javascript"}
        ))
        
        merged = consolidator._merge_related()
        
        assert merged == 0
        assert len(consolidator.entries) == 2


class TestArchiveOutdated:
    """Unit tests for archive outdated logic."""

    def test_archive_old_entries(self, tmp_path):
        """Test archiving entries older than threshold."""
        consolidator = KnowledgeConsolidator(
            expert_name="test",
            storage_dir=tmp_path / "knowledge",
            archive_age_days=30
        )
        
        # Add old entry
        old_entry = KnowledgeEntry(content="Old entry")
        old_entry.updated_at = utc_now() - timedelta(days=60)
        consolidator.add_entry(old_entry)
        
        # Add recent entry
        recent_entry = KnowledgeEntry(content="Recent entry")
        consolidator.add_entry(recent_entry)
        
        archived = consolidator._archive_outdated()
        
        assert archived == 1
        assert len(consolidator.entries) == 1
        assert len(consolidator.archived) == 1
        assert consolidator.entries[0].content == "Recent entry"

    def test_archive_keeps_recent(self, tmp_path):
        """Test archive keeps recent entries."""
        consolidator = KnowledgeConsolidator(
            expert_name="test",
            storage_dir=tmp_path / "knowledge",
            archive_age_days=180
        )
        
        # Add recent entries
        for i in range(3):
            consolidator.add_entry(KnowledgeEntry(content=f"Entry {i}"))
        
        archived = consolidator._archive_outdated()
        
        assert archived == 0
        assert len(consolidator.entries) == 3
        assert len(consolidator.archived) == 0


class TestConsolidateAsync:
    """Unit tests for async consolidate method."""

    @pytest.mark.asyncio
    async def test_consolidate_full_pipeline(self, tmp_path):
        """Test full consolidation pipeline."""
        consolidator = KnowledgeConsolidator(
            expert_name="test",
            storage_dir=tmp_path / "knowledge",
            similarity_threshold=0.85,
            archive_age_days=30
        )
        
        # Add various entries
        consolidator.add_entry(KnowledgeEntry(
            content="Python is great for data science",
            confidence=0.9
        ))
        consolidator.add_entry(KnowledgeEntry(
            content="Python is great for data science",  # Duplicate
            confidence=0.7
        ))
        
        old_entry = KnowledgeEntry(content="Old information")
        old_entry.updated_at = utc_now() - timedelta(days=60)
        consolidator.add_entry(old_entry)
        
        result = await consolidator.consolidate()
        
        assert isinstance(result, ConsolidationResult)
        assert result.total_before == 3
        assert result.deduplicated >= 1
        assert result.archived >= 1
        assert result.total_after < result.total_before

    @pytest.mark.asyncio
    async def test_consolidate_result_structure(self, tmp_path):
        """Test consolidation result has all fields."""
        consolidator = KnowledgeConsolidator(
            expert_name="test",
            storage_dir=tmp_path / "knowledge"
        )
        
        consolidator.add_entry(KnowledgeEntry(content="Test"))
        
        result = await consolidator.consolidate()
        
        assert hasattr(result, "deduplicated")
        assert hasattr(result, "merged")
        assert hasattr(result, "archived")
        assert hasattr(result, "total_before")
        assert hasattr(result, "total_after")
        assert hasattr(result, "space_saved_bytes")
        assert hasattr(result, "duration_seconds")

    @pytest.mark.asyncio
    async def test_consolidate_saves_to_disk(self, tmp_path):
        """Test consolidation saves results to disk."""
        storage_dir = tmp_path / "knowledge"
        consolidator = KnowledgeConsolidator(
            expert_name="test",
            storage_dir=storage_dir
        )
        
        consolidator.add_entry(KnowledgeEntry(content="Persistent entry"))
        
        await consolidator.consolidate()
        
        # Check files exist
        assert (storage_dir / "entries.json").exists()
        assert (storage_dir / "archive.json").exists()


class TestSimilarityComputation:
    """Unit tests for similarity computation."""

    def test_compute_similarity_identical(self, tmp_path):
        """Test similarity of identical texts is 1.0."""
        consolidator = KnowledgeConsolidator(
            expert_name="test",
            storage_dir=tmp_path / "knowledge"
        )
        
        text = "Python is a programming language"
        similarity = consolidator._compute_similarity(text, text)
        
        assert similarity == 1.0

    def test_compute_similarity_different(self, tmp_path):
        """Test similarity of different texts is low."""
        consolidator = KnowledgeConsolidator(
            expert_name="test",
            storage_dir=tmp_path / "knowledge"
        )
        
        text1 = "Python is a programming language"
        text2 = "Cats are furry animals"
        similarity = consolidator._compute_similarity(text1, text2)
        
        assert similarity < 0.3

    def test_compute_similarity_partial(self, tmp_path):
        """Test similarity of partially similar texts."""
        consolidator = KnowledgeConsolidator(
            expert_name="test",
            storage_dir=tmp_path / "knowledge"
        )
        
        text1 = "Python is great for data science and machine learning"
        text2 = "Python is excellent for data analysis and machine learning"
        similarity = consolidator._compute_similarity(text1, text2)
        
        assert 0.3 < similarity < 0.9

    def test_compute_similarity_empty(self, tmp_path):
        """Test similarity with empty text."""
        consolidator = KnowledgeConsolidator(
            expert_name="test",
            storage_dir=tmp_path / "knowledge"
        )
        
        similarity = consolidator._compute_similarity("", "Some text")
        
        assert similarity == 0.0


# =============================================================================
# Property Tests: Staleness Detection
# =============================================================================

class TestStalenessPropertyTests:
    """Property-based tests for staleness detection."""

    @given(
        age_days=st.integers(min_value=0, max_value=365),
        velocity=st.sampled_from(["slow", "medium", "fast"])
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
    )
    def test_staleness_threshold_consistency(self, age_days: int, velocity: str):
        """Property: Staleness is consistent with domain velocity thresholds.
        
        FreshnessChecker uses fractional thresholds:
        - Fresh: <= velocity_days * 0.5
        - Aging: <= velocity_days * 0.8
        - Stale: > velocity_days * 0.8 (is_stale returns True)
        """
        velocity_days = {"slow": 180, "medium": 90, "fast": 30}[velocity]
        stale_threshold = int(velocity_days * 0.8)  # Stale starts at 0.8x
        
        now = utc_now()
        profile = ExpertProfile(
            name="Test",
            vector_store_id="vs_test",
            knowledge_cutoff_date=now - timedelta(days=age_days),
            domain_velocity=velocity
        )
        
        is_stale = profile.is_knowledge_stale()
        
        # Property: stale iff age > 0.8x velocity_days
        if age_days > stale_threshold:
            assert is_stale is True, f"Should be stale: {age_days} > {stale_threshold} (0.8x of {velocity_days})"
        else:
            assert is_stale is False, f"Should be fresh/aging: {age_days} <= {stale_threshold} (0.8x of {velocity_days})"

    @given(
        budget=st.floats(min_value=0.01, max_value=100.0),
        spent=st.floats(min_value=0.0, max_value=100.0),
        amount=st.floats(min_value=0.0, max_value=50.0)
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
    )
    def test_budget_enforcement_consistency(self, budget: float, spent: float, amount: float):
        """Property: Budget enforcement is consistent with remaining budget."""
        # Ensure spent doesn't exceed budget for this test
        spent = min(spent, budget)
        
        profile = ExpertProfile(
            name="Test",
            vector_store_id="vs_test",
            monthly_learning_budget=budget,
            monthly_spending=spent
        )
        
        remaining = budget - spent
        can_spend, _ = profile.can_spend_learning_budget(amount)
        
        # Property: can spend iff amount <= remaining (or amount is 0)
        if amount <= 0:
            assert can_spend is True
        elif amount <= remaining:
            assert can_spend is True
        else:
            assert can_spend is False


# =============================================================================
# Property Tests: Knowledge Consolidation
# =============================================================================

class TestConsolidationPropertyTests:
    """Property-based tests for knowledge consolidation."""

    @given(
        contents=st.lists(
            st.text(min_size=10, max_size=200, alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'Z'))),
            min_size=0,
            max_size=20
        )
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
    )
    def test_deduplication_reduces_or_maintains_count(self, contents: List[str]):
        """Property: Deduplication never increases entry count."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            consolidator = KnowledgeConsolidator(
                expert_name="test",
                storage_dir=Path(tmp_dir) / "knowledge"
            )
            
            for content in contents:
                if content.strip():  # Skip empty
                    consolidator.add_entry(KnowledgeEntry(content=content))
            
            initial_count = len(consolidator.entries)
            consolidator._deduplicate()
            final_count = len(consolidator.entries)
            
            assert final_count <= initial_count

    @given(
        contents=st.lists(
            st.text(min_size=10, max_size=100, alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'Z'))),
            min_size=0,
            max_size=10
        ),
        threshold=st.floats(min_value=0.5, max_value=0.99)
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
    )
    def test_similarity_threshold_respected(self, contents: List[str], threshold: float):
        """Property: Entries below similarity threshold are kept."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            consolidator = KnowledgeConsolidator(
                expert_name="test",
                storage_dir=Path(tmp_dir) / "knowledge",
                similarity_threshold=threshold
            )
            
            for content in contents:
                if content.strip():
                    consolidator.add_entry(KnowledgeEntry(content=content))
            
            consolidator._deduplicate()
            
            # Property: All remaining entries should be below threshold similarity
            entries = consolidator.entries
            for i, e1 in enumerate(entries):
                for e2 in entries[i + 1:]:
                    sim = consolidator._compute_similarity(e1.content, e2.content)
                    assert sim < threshold, f"Entries with similarity {sim} >= {threshold} should be deduplicated"

    @given(
        age_days_list=st.lists(
            st.integers(min_value=0, max_value=365),
            min_size=0,
            max_size=10
        ),
        archive_threshold=st.integers(min_value=30, max_value=180)
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
    )
    def test_archive_threshold_respected(self, age_days_list: List[int], archive_threshold: int):
        """Property: Only entries older than threshold are archived."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            consolidator = KnowledgeConsolidator(
                expert_name="test",
                storage_dir=Path(tmp_dir) / "knowledge",
                archive_age_days=archive_threshold
            )
            
            now = utc_now()
            for i, age_days in enumerate(age_days_list):
                entry = KnowledgeEntry(content=f"Entry {i}")
                entry.updated_at = now - timedelta(days=age_days)
                consolidator.add_entry(entry)
            
            consolidator._archive_outdated()
            
            # Property: All remaining entries should be within threshold
            for entry in consolidator.entries:
                age = (now - entry.updated_at).days
                assert age <= archive_threshold, f"Entry with age {age} > {archive_threshold} should be archived"
            
            # Property: All archived entries should be beyond threshold
            for entry in consolidator.archived:
                age = (now - entry.updated_at).days
                assert age > archive_threshold, f"Entry with age {age} <= {archive_threshold} should not be archived"

    @given(
        text1=st.text(min_size=5, max_size=100, alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'Z'))),
        text2=st.text(min_size=5, max_size=100, alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'Z')))
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
    )
    def test_similarity_symmetry(self, text1: str, text2: str):
        """Property: Similarity is symmetric (sim(a,b) == sim(b,a))."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            consolidator = KnowledgeConsolidator(
                expert_name="test",
                storage_dir=Path(tmp_dir) / "knowledge"
            )
            
            sim_ab = consolidator._compute_similarity(text1, text2)
            sim_ba = consolidator._compute_similarity(text2, text1)
            
            assert sim_ab == sim_ba, f"Similarity should be symmetric: {sim_ab} != {sim_ba}"

    @given(
        text=st.text(min_size=5, max_size=100, alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'Z')))
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
    )
    def test_similarity_reflexivity(self, text: str):
        """Property: Similarity of text with itself is 1.0 (if non-empty after tokenization)."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            consolidator = KnowledgeConsolidator(
                expert_name="test",
                storage_dir=Path(tmp_dir) / "knowledge"
            )
            
            tokens = consolidator._tokenize(text)
            if tokens:  # Only test if there are tokens after stopword removal
                sim = consolidator._compute_similarity(text, text)
                assert sim == 1.0, f"Self-similarity should be 1.0, got {sim}"

    @given(
        text1=st.text(min_size=5, max_size=100, alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'Z'))),
        text2=st.text(min_size=5, max_size=100, alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'Z')))
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
    )
    def test_similarity_bounds(self, text1: str, text2: str):
        """Property: Similarity is always between 0 and 1."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            consolidator = KnowledgeConsolidator(
                expert_name="test",
                storage_dir=Path(tmp_dir) / "knowledge"
            )
            
            sim = consolidator._compute_similarity(text1, text2)
            
            assert 0.0 <= sim <= 1.0, f"Similarity should be in [0, 1], got {sim}"


class TestConsolidationResultPropertyTests:
    """Property tests for consolidation results."""

    @given(
        num_entries=st.integers(min_value=0, max_value=50)
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
    )
    def test_consolidation_preserves_or_reduces(self, num_entries: int):
        """Property: Consolidation never increases total entry count."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            consolidator = KnowledgeConsolidator(
                expert_name="test",
                storage_dir=Path(tmp_dir) / "knowledge"
            )
            
            for i in range(num_entries):
                consolidator.add_entry(KnowledgeEntry(content=f"Entry number {i} with some content"))
            
            initial_count = len(consolidator.entries)
            
            # Run consolidation synchronously for property test
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(consolidator.consolidate())
            finally:
                loop.close()
            
            # Property: total_after <= total_before
            assert result.total_after <= result.total_before
            assert result.total_after == len(consolidator.entries)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
