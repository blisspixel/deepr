"""Tests for profile_store module.

Requirements: 1.2 - ExpertProfile Refactoring
"""

import json
import pytest
from datetime import datetime, timezone
from pathlib import Path

from deepr.experts.profile import ExpertProfile
from deepr.experts.profile_store import (
    ExpertStore,
    PROFILE_SCHEMA_VERSION,
    migrate_profile_data,
    migration,
    _MIGRATIONS,
)


class TestProfileSchemaVersion:
    """Tests for schema versioning."""

    def test_schema_version_is_set(self):
        """Test that PROFILE_SCHEMA_VERSION is defined."""
        assert PROFILE_SCHEMA_VERSION >= 1

    def test_migration_decorator_registers(self):
        """Test that @migration decorator registers functions."""
        # There should be at least one migration registered
        assert len(_MIGRATIONS) > 0


class TestMigrations:
    """Tests for schema migrations."""

    def test_migrate_v1_to_v2(self):
        """Test migration from v1 to v2 schema."""
        v1_data = {
            "name": "test-expert",
            "vector_store_id": "vs_123",
            "description": "Test expert",
            "domain": "testing",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            # V1 didn't have these fields
            "learning_budget": 10.0,  # Old name
        }

        migrated = migrate_profile_data(v1_data)

        assert migrated.get("schema_version") == PROFILE_SCHEMA_VERSION
        assert "provider" in migrated
        assert "model" in migrated
        assert "refresh_history" in migrated

    def test_migrate_already_current(self):
        """Test migration skips if already at current version."""
        current_data = {
            "name": "test-expert",
            "vector_store_id": "vs_123",
            "schema_version": PROFILE_SCHEMA_VERSION,
        }

        migrated = migrate_profile_data(current_data)
        assert migrated == current_data


class TestExpertStore:
    """Tests for ExpertStore class."""

    @pytest.fixture
    def store(self, tmp_path):
        """Create a temporary ExpertStore."""
        return ExpertStore(base_path=str(tmp_path / "experts"))

    @pytest.fixture
    def sample_profile(self):
        """Create a sample ExpertProfile."""
        return ExpertProfile(
            name="test-expert",
            vector_store_id="vs_test_123",
            description="Test expert for unit tests",
            domain="testing",
        )

    def test_save_and_load(self, store, sample_profile):
        """Test saving and loading a profile."""
        store.save(sample_profile)

        loaded = store.load("test-expert")
        assert loaded is not None
        assert loaded.name == "test-expert"
        assert loaded.vector_store_id == "vs_test_123"
        assert loaded.description == "Test expert for unit tests"

    def test_save_creates_directories(self, store, sample_profile):
        """Test that save creates required directories."""
        store.save(sample_profile)

        expert_dir = store._get_expert_dir("test-expert")
        assert expert_dir.exists()
        assert (expert_dir / "documents").exists()
        assert (expert_dir / "knowledge").exists()
        assert (expert_dir / "conversations").exists()
        assert (expert_dir / "beliefs").exists()

    def test_save_includes_schema_version(self, store, sample_profile, tmp_path):
        """Test that saved profiles include schema version."""
        store.save(sample_profile)

        profile_path = store._get_profile_path("test-expert")
        with open(profile_path) as f:
            data = json.load(f)

        assert data.get("schema_version") == PROFILE_SCHEMA_VERSION

    def test_load_nonexistent(self, store):
        """Test loading a nonexistent profile returns None."""
        result = store.load("nonexistent")
        assert result is None

    def test_exists(self, store, sample_profile):
        """Test exists() method."""
        assert not store.exists("test-expert")

        store.save(sample_profile)
        assert store.exists("test-expert")

    def test_delete(self, store, sample_profile):
        """Test delete() method."""
        store.save(sample_profile)
        assert store.exists("test-expert")

        result = store.delete("test-expert")
        assert result is True
        assert not store.exists("test-expert")

    def test_delete_nonexistent(self, store):
        """Test delete returns False for nonexistent profile."""
        result = store.delete("nonexistent")
        assert result is False

    def test_list_all(self, store):
        """Test list_all() returns all profiles."""
        # Create multiple experts
        for i in range(3):
            profile = ExpertProfile(
                name=f"expert-{i}",
                vector_store_id=f"vs_{i}",
            )
            store.save(profile)

        profiles = store.list_all()
        assert len(profiles) == 3

    def test_list_all_sorted_by_updated_at(self, store):
        """Test list_all() returns profiles sorted by updated_at."""
        # Create experts with different update times
        from datetime import timedelta

        base_time = datetime.now(timezone.utc)

        for i in range(3):
            profile = ExpertProfile(
                name=f"expert-{i}",
                vector_store_id=f"vs_{i}",
                updated_at=base_time - timedelta(days=i),
            )
            store.save(profile)

        profiles = store.list_all()

        # Most recently updated should be first
        for i in range(len(profiles) - 1):
            assert profiles[i].updated_at >= profiles[i + 1].updated_at

    def test_rename(self, store, sample_profile):
        """Test rename() method."""
        store.save(sample_profile)
        store.rename("test-expert", "renamed-expert")

        assert not store.exists("test-expert")
        assert store.exists("renamed-expert")

        loaded = store.load("renamed-expert")
        assert loaded.name == "renamed-expert"

    def test_rename_nonexistent_raises(self, store):
        """Test rename raises for nonexistent source."""
        with pytest.raises(ValueError, match="not found"):
            store.rename("nonexistent", "new-name")

    def test_rename_existing_target_raises(self, store, sample_profile):
        """Test rename raises if target exists."""
        store.save(sample_profile)

        other = ExpertProfile(name="other-expert", vector_store_id="vs_other")
        store.save(other)

        with pytest.raises(ValueError, match="already exists"):
            store.rename("test-expert", "other-expert")

    def test_backup(self, store, sample_profile):
        """Test backup() method."""
        store.save(sample_profile)
        backup_path = store.backup("test-expert")

        assert backup_path is not None
        assert backup_path.exists()
        assert (backup_path / "profile.json").exists()

    def test_backup_nonexistent(self, store):
        """Test backup returns None for nonexistent profile."""
        result = store.backup("nonexistent")
        assert result is None


class TestBulkOperations:
    """Tests for bulk ExpertStore operations."""

    @pytest.fixture
    def store(self, tmp_path):
        """Create a temporary ExpertStore."""
        return ExpertStore(base_path=str(tmp_path / "experts"))

    def test_get_experts_by_domain(self, store):
        """Test get_experts_by_domain() method."""
        # Create experts in different domains
        domains = ["python", "python", "rust", "python"]
        for i, domain in enumerate(domains):
            profile = ExpertProfile(
                name=f"expert-{i}",
                vector_store_id=f"vs_{i}",
                domain=domain,
            )
            store.save(profile)

        python_experts = store.get_experts_by_domain("python")
        assert len(python_experts) == 3

        rust_experts = store.get_experts_by_domain("rust")
        assert len(rust_experts) == 1

    def test_get_total_research_cost(self, store):
        """Test get_total_research_cost() method."""
        costs = [1.5, 2.5, 3.0]
        for i, cost in enumerate(costs):
            profile = ExpertProfile(
                name=f"expert-{i}",
                vector_store_id=f"vs_{i}",
                total_research_cost=cost,
            )
            store.save(profile)

        total = store.get_total_research_cost()
        assert total == sum(costs)

    def test_export_all(self, store, tmp_path):
        """Test export_all() method."""
        # Create experts
        for i in range(3):
            profile = ExpertProfile(
                name=f"expert-{i}",
                vector_store_id=f"vs_{i}",
            )
            store.save(profile)

        export_dir = tmp_path / "export"
        count = store.export_all(export_dir)

        assert count == 3
        assert export_dir.exists()
        assert len(list(export_dir.glob("*.json"))) == 3


class TestPathHelpers:
    """Tests for path helper methods."""

    @pytest.fixture
    def store(self, tmp_path):
        """Create a temporary ExpertStore."""
        return ExpertStore(base_path=str(tmp_path / "experts"))

    def test_get_documents_dir(self, store):
        """Test get_documents_dir() returns correct path."""
        path = store.get_documents_dir("test-expert")
        assert path.name == "documents"
        assert "test-expert" in str(path.parent)

    def test_get_knowledge_dir(self, store):
        """Test get_knowledge_dir() returns correct path."""
        path = store.get_knowledge_dir("test-expert")
        assert path.name == "knowledge"
        assert "test-expert" in str(path.parent)

    def test_get_conversations_dir(self, store):
        """Test get_conversations_dir() returns correct path."""
        path = store.get_conversations_dir("test-expert")
        assert path.name == "conversations"
        assert "test-expert" in str(path.parent)

    def test_get_beliefs_dir(self, store):
        """Test get_beliefs_dir() returns correct path."""
        path = store.get_beliefs_dir("test-expert")
        assert path.name == "beliefs"
        assert "test-expert" in str(path.parent)
