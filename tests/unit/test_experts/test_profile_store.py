"""Tests for profile_store module.

Requirements: 1.2 - ExpertProfile Refactoring
"""

import json
from datetime import UTC, datetime

import pytest

from deepr.experts.profile import ExpertProfile
from deepr.experts.profile_store import (
    _MIGRATIONS,
    PROFILE_SCHEMA_VERSION,
    ExpertStore,
    migrate_profile_data,
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
        assert migrated["roster_tier"] == "standard"

    def test_migrate_already_current(self):
        """Test migration skips if already at current version."""
        current_data = {
            "name": "test-expert",
            "vector_store_id": "vs_123",
            "schema_version": PROFILE_SCHEMA_VERSION,
        }

        migrated = migrate_profile_data(current_data)
        assert migrated == current_data

    def test_future_profile_schema_is_not_silently_downgraded(self):
        future_data = {
            "name": "future-expert",
            "vector_store_id": "vs_future",
            "schema_version": PROFILE_SCHEMA_VERSION + 1,
        }

        with pytest.raises(ValueError, match="newer than supported"):
            migrate_profile_data(future_data)


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
        assert loaded.schema_version == PROFILE_SCHEMA_VERSION
        assert loaded.roster_tier == "standard"

    def test_load_normalizes_string_schema_version_before_comparing_migration(self, store, sample_profile):
        profile_path = store._get_profile_path(sample_profile.name)
        profile_path.parent.mkdir(parents=True)
        payload = sample_profile.to_dict()
        payload["schema_version"] = "4"
        payload.pop("roster_tier", None)
        profile_path.write_text(json.dumps(payload), encoding="utf-8")

        loaded = store.load(sample_profile.name)

        assert loaded is not None
        assert loaded.roster_tier == "standard"
        assert json.loads(profile_path.read_text(encoding="utf-8"))["schema_version"] == PROFILE_SCHEMA_VERSION

    def test_migration_reloads_under_save_lock_before_persisting(
        self,
        store,
        sample_profile,
        monkeypatch,
        caplog,
    ):
        profile_path = store._get_profile_path(sample_profile.name)
        profile_path.parent.mkdir(parents=True)
        legacy = sample_profile.to_dict()
        legacy["schema_version"] = 4
        legacy.pop("roster_tier", None)
        profile_path.write_text(json.dumps(legacy), encoding="utf-8")

        concurrent = sample_profile.to_dict()
        concurrent["schema_version"] = PROFILE_SCHEMA_VERSION
        concurrent["description"] = "saved while migration was waiting"
        concurrent["roster_tier"] = "flagship"

        class CompletingSave:
            def __init__(self, *_args, **_kwargs):
                pass

            def __enter__(self):
                profile_path.write_text(json.dumps(concurrent), encoding="utf-8")
                return self

            def __exit__(self, *_args):
                return False

        monkeypatch.setattr("deepr.experts.profile_store.FileLock", CompletingSave)

        with caplog.at_level("INFO", logger="deepr.experts.profile_store"):
            loaded = store.load(sample_profile.name)

        assert loaded is not None
        assert loaded.description == "saved while migration was waiting"
        assert loaded.roster_tier == "flagship"
        assert json.loads(profile_path.read_text(encoding="utf-8"))["description"] == concurrent["description"]
        assert "Migrated profile" not in caplog.text

    @pytest.mark.parametrize("invalid_version", [True, 0, -1, 4.5, "not-a-version"])
    def test_load_rejects_invalid_schema_versions(self, store, sample_profile, invalid_version):
        profile_path = store._get_profile_path(sample_profile.name)
        profile_path.parent.mkdir(parents=True)
        payload = sample_profile.to_dict()
        payload["schema_version"] = invalid_version
        profile_path.write_text(json.dumps(payload), encoding="utf-8")

        with pytest.raises(ValueError, match="schema_version"):
            store.load(sample_profile.name)

    def test_flagship_roster_tier_round_trips(self, store, sample_profile):
        sample_profile.roster_tier = "flagship"
        store.save(sample_profile)

        loaded = store.load(sample_profile.name)
        assert loaded is not None
        assert loaded.roster_tier == "flagship"

    def test_invalid_roster_tier_fails_closed(self):
        with pytest.raises(ValueError, match="roster_tier"):
            ExpertProfile(name="test", vector_store_id="vs", roster_tier="best according to model")

    def test_find_existing_dir_returns_validated_directory(self, store, sample_profile):
        store.save(sample_profile)

        resolved = store.find_existing_dir(sample_profile.name)

        assert resolved == (store.base_path / "test-expert").resolve()
        assert resolved is not None
        assert resolved.is_relative_to(store.base_path.resolve())

    def test_find_existing_dir_returns_none_for_missing_root(self, tmp_path):
        store = ExpertStore(base_path=str(tmp_path / "missing"), create=False)

        assert store.find_existing_dir("../../missing") is None

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
        assert sample_profile.schema_version == PROFILE_SCHEMA_VERSION

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

        base_time = datetime.now(UTC)

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
