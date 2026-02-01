"""Unit tests for ExpertProfile - no API calls required.

Tests the expert profile data structure, serialization, freshness detection,
and programmatic date injection without making any external API calls.
"""

import pytest
from datetime import datetime, timedelta
from deepr.experts.profile import (
    ExpertProfile,
    ExpertStore,
    get_expert_system_message,
    DEFAULT_EXPERT_SYSTEM_MESSAGE
)


class TestExpertProfileDataStructure:
    """Test ExpertProfile dataclass functionality."""

    def test_expert_profile_initialization(self):
        """Test creating an expert profile with minimal fields."""
        profile = ExpertProfile(
            name="Test Expert",
            vector_store_id="vs_test123"
        )

        assert profile.name == "Test Expert"
        assert profile.vector_store_id == "vs_test123"
        assert profile.domain_velocity == "medium"  # Default
        assert profile.refresh_frequency_days == 90  # Default
        assert profile.conversations == 0
        assert profile.research_triggered == 0
        assert profile.total_research_cost == 0.0

    def test_expert_profile_with_full_metadata(self):
        """Test creating an expert with all fields."""
        now = datetime.utcnow()

        profile = ExpertProfile(
            name="Azure Expert",
            vector_store_id="vs_azure123",
            description="Azure architecture expert",
            domain="Azure Cloud",
            created_at=now,
            updated_at=now,
            source_files=["azure-guide.pdf", "best-practices.md"],
            research_jobs=["job-001", "job-002"],
            total_documents=5,
            knowledge_cutoff_date=now,
            last_knowledge_refresh=now,
            refresh_frequency_days=30,
            domain_velocity="fast",
            provider="openai",
            model="gpt-4-turbo"
        )

        assert profile.name == "Azure Expert"
        assert profile.description == "Azure architecture expert"
        assert profile.domain_velocity == "fast"
        assert profile.refresh_frequency_days == 30
        assert len(profile.source_files) == 2
        assert len(profile.research_jobs) == 2
        assert profile.total_documents == 5


class TestKnowledgeFreshnessDetection:
    """Test knowledge freshness detection logic."""

    def test_is_knowledge_stale_no_cutoff(self):
        """Test that expert with no cutoff is considered stale."""
        profile = ExpertProfile(
            name="Test Expert",
            vector_store_id="vs_test",
            knowledge_cutoff_date=None
        )

        assert profile.is_knowledge_stale() is True

    def test_is_knowledge_stale_fast_domain_fresh(self):
        """Test fast domain with fresh knowledge (< 30 days)."""
        now = datetime.utcnow()
        recent = now - timedelta(days=15)  # 15 days old

        profile = ExpertProfile(
            name="AI Expert",
            vector_store_id="vs_ai",
            knowledge_cutoff_date=recent,
            domain_velocity="fast"
        )

        assert profile.is_knowledge_stale() is False

    def test_is_knowledge_stale_fast_domain_stale(self):
        """Test fast domain with stale knowledge (> 30 days)."""
        now = datetime.utcnow()
        old = now - timedelta(days=45)  # 45 days old

        profile = ExpertProfile(
            name="AI Expert",
            vector_store_id="vs_ai",
            knowledge_cutoff_date=old,
            domain_velocity="fast"
        )

        assert profile.is_knowledge_stale() is True

    def test_is_knowledge_stale_medium_domain_fresh(self):
        """Test medium domain with fresh knowledge (< 90 days)."""
        now = datetime.utcnow()
        recent = now - timedelta(days=60)  # 60 days old

        profile = ExpertProfile(
            name="Tech Expert",
            vector_store_id="vs_tech",
            knowledge_cutoff_date=recent,
            domain_velocity="medium"
        )

        assert profile.is_knowledge_stale() is False

    def test_is_knowledge_stale_medium_domain_stale(self):
        """Test medium domain with stale knowledge (> 90 days)."""
        now = datetime.utcnow()
        old = now - timedelta(days=120)  # 120 days old

        profile = ExpertProfile(
            name="Tech Expert",
            vector_store_id="vs_tech",
            knowledge_cutoff_date=old,
            domain_velocity="medium"
        )

        assert profile.is_knowledge_stale() is True

    def test_is_knowledge_stale_slow_domain_fresh(self):
        """Test slow domain with fresh knowledge (< 180 days)."""
        now = datetime.utcnow()
        recent = now - timedelta(days=100)  # 100 days old

        profile = ExpertProfile(
            name="Legal Expert",
            vector_store_id="vs_legal",
            knowledge_cutoff_date=recent,
            domain_velocity="slow"
        )

        assert profile.is_knowledge_stale() is False

    def test_is_knowledge_stale_slow_domain_stale(self):
        """Test slow domain with stale knowledge (> 180 days)."""
        now = datetime.utcnow()
        old = now - timedelta(days=200)  # 200 days old

        profile = ExpertProfile(
            name="Legal Expert",
            vector_store_id="vs_legal",
            knowledge_cutoff_date=old,
            domain_velocity="slow"
        )

        assert profile.is_knowledge_stale() is True


class TestFreshnessStatus:
    """Test detailed freshness status reporting."""

    def test_get_freshness_status_incomplete(self):
        """Test status for expert with no knowledge cutoff."""
        profile = ExpertProfile(
            name="New Expert",
            vector_store_id="vs_new",
            knowledge_cutoff_date=None
        )

        status = profile.get_freshness_status()

        assert status["status"] == "incomplete"
        assert "learning" in status["message"].lower()
        assert "action_required" in status
        assert "deepr expert learn" in status["action_required"]

    def test_get_freshness_status_fresh(self):
        """Test status for expert with fresh knowledge.
        
        FreshnessChecker uses 50% of threshold as "fresh" boundary.
        For medium domain (90 days), fresh is < 45 days.
        """
        now = datetime.utcnow()
        recent = now - timedelta(days=30)  # 30 days old (threshold is 90, fresh < 45)

        profile = ExpertProfile(
            name="Fresh Expert",
            vector_store_id="vs_fresh",
            knowledge_cutoff_date=recent,
            domain_velocity="medium"
        )

        status = profile.get_freshness_status()

        assert status["status"] == "fresh"
        assert status["age_days"] == 30
        assert status["threshold_days"] == 90
        # FreshnessChecker returns "Knowledge is up to date. No action needed."
        assert "up to date" in status["message"].lower() or "no action" in status["message"].lower()
        assert status["action_required"] is None

    def test_get_freshness_status_aging(self):
        """Test status for expert with aging knowledge (> 50% but < 80% of threshold).
        
        FreshnessChecker thresholds:
        - Fresh: < 50% of velocity_days (< 45 days for medium)
        - Aging: 50-80% of velocity_days (45-72 days for medium)
        - Stale: 80-150% of velocity_days (72-135 days for medium)
        - Critical: > 150% of velocity_days (> 135 days for medium)
        
        For medium domain (90 days), aging is 45-72 days.
        """
        now = datetime.utcnow()
        aging = now - timedelta(days=60)  # 60 days old (in aging range: 45-72)

        profile = ExpertProfile(
            name="Aging Expert",
            vector_store_id="vs_aging",
            knowledge_cutoff_date=aging,
            domain_velocity="medium"
        )

        status = profile.get_freshness_status()

        assert status["status"] == "aging"
        assert status["age_days"] == 60
        assert status["threshold_days"] == 90
        # FreshnessChecker returns "Knowledge is X days old. Consider refreshing soon."
        assert "consider" in status["message"].lower() or "refresh" in status["message"].lower()
        assert status["action_required"] is not None

    def test_get_freshness_status_stale(self):
        """Test status for expert with stale knowledge (> threshold).
        
        For medium domain (90 days), stale is 72-135 days (80-150% of threshold).
        """
        now = datetime.utcnow()
        stale = now - timedelta(days=120)  # 120 days old (in stale range: 72-135)

        profile = ExpertProfile(
            name="Stale Expert",
            vector_store_id="vs_stale",
            knowledge_cutoff_date=stale,
            domain_velocity="medium"
        )

        status = profile.get_freshness_status()

        assert status["status"] == "stale"
        assert status["age_days"] == 120
        assert status["threshold_days"] == 90
        # FreshnessChecker returns "Knowledge is stale (X days). Recommend refreshing..."
        assert "stale" in status["message"].lower() or "120" in status["message"]
        assert status["action_required"] is not None
        assert "refresh" in status["action_required"].lower()


class TestProgrammaticDateInjection:
    """Test that get_expert_system_message uses programmatic dates."""

    def test_system_message_contains_current_date(self):
        """Test that system message contains today's date (not hardcoded)."""
        now = datetime.utcnow()
        today_str = now.strftime("%Y-%m-%d")
        today_readable = now.strftime("%B %d, %Y")

        message = get_expert_system_message()

        # Should contain both formats of today's date
        assert today_str in message
        assert today_readable in message

        # Should NOT contain hardcoded old dates
        assert "2024" not in message
        assert "January 2025" not in message

    def test_system_message_calculates_knowledge_age(self):
        """Test that system message correctly calculates knowledge age."""
        now = datetime.utcnow()
        old_cutoff = now - timedelta(days=120)

        message = get_expert_system_message(
            knowledge_cutoff_date=old_cutoff,
            domain_velocity="medium"
        )

        # Should show 120 days old
        assert "120 days old" in message

        # Should show the cutoff date
        cutoff_str = old_cutoff.strftime("%Y-%m-%d")
        assert cutoff_str in message

    def test_system_message_shows_stale_status(self):
        """Test that system message correctly identifies stale knowledge."""
        now = datetime.utcnow()

        # Fast domain with old knowledge (>30 days)
        old_cutoff = now - timedelta(days=45)
        message = get_expert_system_message(
            knowledge_cutoff_date=old_cutoff,
            domain_velocity="fast"
        )

        assert "STALE - RESEARCH REQUIRED" in message
        assert "fast" in message
        assert "30 days" in message  # Fast domain threshold

    def test_system_message_shows_fresh_status(self):
        """Test that system message correctly identifies fresh knowledge."""
        now = datetime.utcnow()

        # Medium domain with recent knowledge (<90 days)
        recent_cutoff = now - timedelta(days=30)
        message = get_expert_system_message(
            knowledge_cutoff_date=recent_cutoff,
            domain_velocity="medium"
        )

        assert "FRESH" in message
        assert "STALE" not in message

    def test_system_message_domain_velocity_thresholds(self):
        """Test that system message respects domain velocity thresholds."""
        now = datetime.utcnow()
        cutoff = now - timedelta(days=60)

        # Slow domain (180 day threshold) - should be fresh
        slow_message = get_expert_system_message(cutoff, "slow")
        assert "FRESH" in slow_message
        assert "180 days" in slow_message

        # Medium domain (90 day threshold) - should be fresh
        medium_message = get_expert_system_message(cutoff, "medium")
        assert "FRESH" in medium_message
        assert "90 days" in medium_message

        # Fast domain (30 day threshold) - should be stale
        fast_message = get_expert_system_message(cutoff, "fast")
        assert "STALE" in fast_message
        assert "30 days" in fast_message

    def test_default_expert_system_message_exists(self):
        """Test that DEFAULT_EXPERT_SYSTEM_MESSAGE constant exists."""
        assert DEFAULT_EXPERT_SYSTEM_MESSAGE is not None
        assert isinstance(DEFAULT_EXPERT_SYSTEM_MESSAGE, str)
        assert len(DEFAULT_EXPERT_SYSTEM_MESSAGE) > 0

        # Should contain key concepts
        assert "TEMPORAL AWARENESS" in DEFAULT_EXPERT_SYSTEM_MESSAGE
        assert "Beginner's Mind" in DEFAULT_EXPERT_SYSTEM_MESSAGE


class TestExpertProfileSerialization:
    """Test JSON serialization and deserialization."""

    def test_to_dict_conversion(self):
        """Test converting profile to dictionary."""
        now = datetime.utcnow()

        profile = ExpertProfile(
            name="Test Expert",
            vector_store_id="vs_test",
            description="Test description",
            knowledge_cutoff_date=now,
            domain_velocity="fast"
        )

        data = profile.to_dict()

        assert isinstance(data, dict)
        assert data["name"] == "Test Expert"
        assert data["vector_store_id"] == "vs_test"
        assert data["description"] == "Test description"
        assert data["domain_velocity"] == "fast"

        # Datetimes should be ISO format strings
        assert isinstance(data["created_at"], str)
        assert isinstance(data["knowledge_cutoff_date"], str)

    def test_from_dict_conversion(self):
        """Test creating profile from dictionary."""
        now = datetime.utcnow()

        data = {
            "name": "Test Expert",
            "vector_store_id": "vs_test",
            "description": "Test description",
            "domain_velocity": "medium",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "knowledge_cutoff_date": now.isoformat(),
            "source_files": ["file1.pdf"],
            "research_jobs": [],
            "total_documents": 1,
            "conversations": 0,
            "research_triggered": 0,
            "total_research_cost": 0.0,
            "provider": "openai",
            "model": "gpt-4-turbo",
            "refresh_frequency_days": 90,
            "last_knowledge_refresh": None,
            "system_message": None,
            "temperature": 0.7,
            "max_tokens": 4000,
            "domain": None
        }

        profile = ExpertProfile.from_dict(data)

        assert profile.name == "Test Expert"
        assert profile.vector_store_id == "vs_test"
        assert profile.domain_velocity == "medium"
        assert isinstance(profile.created_at, datetime)
        assert isinstance(profile.knowledge_cutoff_date, datetime)

    def test_roundtrip_serialization(self):
        """Test that to_dict -> from_dict preserves data."""
        now = datetime.utcnow()

        original = ExpertProfile(
            name="Roundtrip Expert",
            vector_store_id="vs_roundtrip",
            description="Testing roundtrip",
            knowledge_cutoff_date=now,
            domain_velocity="fast",
            source_files=["doc1.pdf", "doc2.md"],
            total_documents=2
        )

        # Convert to dict and back
        data = original.to_dict()
        restored = ExpertProfile.from_dict(data)

        assert restored.name == original.name
        assert restored.vector_store_id == original.vector_store_id
        assert restored.description == original.description
        assert restored.domain_velocity == original.domain_velocity
        assert restored.source_files == original.source_files
        assert restored.total_documents == original.total_documents


class TestExpertStoreFilenames:
    """Test ExpertStore filename sanitization.
    
    Note: The current implementation uses a folder structure:
    data/experts/[expert_name]/profile.json
    """

    def test_get_profile_path_sanitization(self, tmp_path):
        """Test that profile paths are sanitized and use folder structure."""
        store = ExpertStore(base_path=str(tmp_path))

        # Test with spaces - should create folder with sanitized name
        path1 = store._get_profile_path("Azure Expert")
        assert "azure_expert" in str(path1).lower()
        assert "profile.json" in str(path1).lower()

        # Test with special characters
        path2 = store._get_profile_path("Python/Django Expert!")
        assert "profile.json" in str(path2).lower()
        # Special chars should be removed or replaced
        assert "/" not in str(path2).split(str(tmp_path))[-1].replace("\\", "/").split("/")[0]

        # Test with hyphens (should be preserved)
        path3 = store._get_profile_path("AI-ML-Expert")
        assert "ai-ml-expert" in str(path3).lower()
        assert "profile.json" in str(path3).lower()

    def test_store_creates_directory(self, tmp_path):
        """Test that ExpertStore creates directory if missing."""
        expert_dir = tmp_path / "experts"
        assert not expert_dir.exists()

        store = ExpertStore(base_path=str(expert_dir))

        assert expert_dir.exists()
        assert expert_dir.is_dir()


class TestExpertStoreSaveLoad:
    """Test ExpertStore save and load operations."""

    def test_save_and_load_expert(self, tmp_path):
        """Test saving and loading an expert profile."""
        store = ExpertStore(base_path=str(tmp_path))

        now = datetime.utcnow()
        profile = ExpertProfile(
            name="Test Expert",
            vector_store_id="vs_test",
            description="Test expert",
            knowledge_cutoff_date=now,
            domain_velocity="medium"
        )

        # Save
        store.save(profile)

        # Load
        loaded = store.load("Test Expert")

        assert loaded is not None
        assert loaded.name == profile.name
        assert loaded.vector_store_id == profile.vector_store_id
        assert loaded.description == profile.description
        assert loaded.domain_velocity == profile.domain_velocity

    def test_load_nonexistent_expert(self, tmp_path):
        """Test loading an expert that doesn't exist."""
        store = ExpertStore(base_path=str(tmp_path))

        loaded = store.load("Nonexistent Expert")

        assert loaded is None

    def test_exists_check(self, tmp_path):
        """Test checking if expert exists."""
        store = ExpertStore(base_path=str(tmp_path))

        profile = ExpertProfile(
            name="Existing Expert",
            vector_store_id="vs_exists"
        )

        assert store.exists("Existing Expert") is False

        store.save(profile)

        assert store.exists("Existing Expert") is True

    def test_delete_expert(self, tmp_path):
        """Test deleting an expert profile."""
        store = ExpertStore(base_path=str(tmp_path))

        profile = ExpertProfile(
            name="Delete Me",
            vector_store_id="vs_delete"
        )

        store.save(profile)
        assert store.exists("Delete Me") is True

        success = store.delete("Delete Me")

        assert success is True
        assert store.exists("Delete Me") is False

    def test_delete_nonexistent_expert(self, tmp_path):
        """Test deleting an expert that doesn't exist."""
        store = ExpertStore(base_path=str(tmp_path))

        success = store.delete("Nonexistent")

        assert success is False

    def test_list_all_experts_empty(self, tmp_path):
        """Test listing experts when none exist."""
        store = ExpertStore(base_path=str(tmp_path))

        experts = store.list_all()

        assert experts == []

    def test_list_all_experts(self, tmp_path):
        """Test listing multiple experts."""
        store = ExpertStore(base_path=str(tmp_path))

        # Create multiple experts
        for i in range(3):
            profile = ExpertProfile(
                name=f"Expert {i}",
                vector_store_id=f"vs_{i}"
            )
            store.save(profile)

        experts = store.list_all()

        assert len(experts) == 3
        names = [e.name for e in experts]
        assert "Expert 0" in names
        assert "Expert 1" in names
        assert "Expert 2" in names

    def test_list_all_sorts_by_updated_at(self, tmp_path):
        """Test that list_all sorts by updated_at descending."""
        import time
        store = ExpertStore(base_path=str(tmp_path))

        # Create experts with different timestamps
        profile1 = ExpertProfile(
            name="First Expert",
            vector_store_id="vs_1"
        )
        store.save(profile1)

        time.sleep(0.01)  # Small delay to ensure different timestamps

        profile2 = ExpertProfile(
            name="Second Expert",
            vector_store_id="vs_2"
        )
        store.save(profile2)

        experts = store.list_all()

        # Should be sorted newest first
        assert len(experts) == 2
        assert experts[0].name == "Second Expert"
        assert experts[1].name == "First Expert"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
