"""Tests for core schema versioning infrastructure."""

import json

from deepr.core.schema_version import (
    CURRENT_VERSIONS,
    SchemaVersion,
    _compare_versions,
    _migrations,
    add_schema_version,
    ensure_versioned,
    get_migration_path,
    get_schema_version,
    get_version_string,
    load_versioned_json,
    migrate,
    needs_migration,
    register_migration,
    save_versioned_json,
)


class TestSchemaVersion:
    """Test SchemaVersion dataclass."""

    def test_to_dict(self):
        sv = SchemaVersion(
            schema_type="worldview",
            version="1.0.0",
            created_at="2025-01-01T00:00:00+00:00",
        )
        d = sv.to_dict()
        assert d["schema_type"] == "worldview"
        assert d["version"] == "1.0.0"
        assert d["migrated_from"] is None

    def test_to_dict_with_migrated_from(self):
        sv = SchemaVersion(
            schema_type="trace",
            version="2.0.0",
            created_at="2025-01-01T00:00:00+00:00",
            migrated_from="1.0.0",
        )
        d = sv.to_dict()
        assert d["migrated_from"] == "1.0.0"

    def test_from_dict_defaults(self):
        sv = SchemaVersion.from_dict({})
        assert sv.schema_type == "unknown"
        assert sv.version == "0.0.0"
        assert sv.migrated_from is None

    def test_from_dict_roundtrip(self):
        original = SchemaVersion(
            schema_type="memory",
            version="1.0.0",
            created_at="2025-06-01T12:00:00+00:00",
            migrated_from="0.9.0",
        )
        restored = SchemaVersion.from_dict(original.to_dict())
        assert restored.schema_type == original.schema_type
        assert restored.version == original.version
        assert restored.migrated_from == original.migrated_from


class TestCompareVersions:
    """Test version comparison logic."""

    def test_equal_versions(self):
        assert _compare_versions("1.0.0", "1.0.0") == 0

    def test_less_than(self):
        assert _compare_versions("1.0.0", "2.0.0") == -1
        assert _compare_versions("1.0.0", "1.1.0") == -1
        assert _compare_versions("1.0.0", "1.0.1") == -1

    def test_greater_than(self):
        assert _compare_versions("2.0.0", "1.0.0") == 1
        assert _compare_versions("1.1.0", "1.0.0") == 1

    def test_different_length_versions(self):
        assert _compare_versions("1.0", "1.0.0") == 0
        assert _compare_versions("1.0", "1.0.1") == -1

    def test_invalid_version_string(self):
        assert _compare_versions("invalid", "1.0.0") == -1
        assert _compare_versions("1.0.0", "invalid") == 1


class TestAddSchemaVersion:
    """Test add_schema_version function."""

    def test_adds_version_field(self):
        data = {"key": "value"}
        result = add_schema_version(data, "worldview")
        assert "schema_version" in result
        assert result["schema_version"]["schema_type"] == "worldview"
        assert result["schema_version"]["version"] == CURRENT_VERSIONS["worldview"]

    def test_preserves_original_data(self):
        data = {"beliefs": [1, 2, 3], "gaps": []}
        result = add_schema_version(data, "worldview")
        assert result["beliefs"] == [1, 2, 3]
        assert result["gaps"] == []

    def test_custom_version(self):
        data = {"key": "value"}
        result = add_schema_version(data, "worldview", "3.5.0")
        assert result["schema_version"]["version"] == "3.5.0"

    def test_unknown_schema_type_defaults_to_1_0_0(self):
        data = {"key": "value"}
        result = add_schema_version(data, "unknown_type")
        assert result["schema_version"]["version"] == "1.0.0"


class TestGetSchemaVersion:
    """Test get_schema_version function."""

    def test_returns_none_for_unversioned(self):
        assert get_schema_version({"key": "value"}) is None

    def test_returns_schema_version(self):
        data = add_schema_version({"key": "value"}, "worldview")
        sv = get_schema_version(data)
        assert sv is not None
        assert sv.schema_type == "worldview"


class TestGetVersionString:
    """Test get_version_string function."""

    def test_returns_0_0_0_for_unversioned(self):
        assert get_version_string({"key": "value"}) == "0.0.0"

    def test_returns_version(self):
        data = add_schema_version({"key": "value"}, "worldview", "2.1.0")
        assert get_version_string(data) == "2.1.0"


class TestNeedsMigration:
    """Test needs_migration function."""

    def test_unversioned_data_needs_migration(self):
        assert needs_migration({"key": "value"}, "worldview") is True

    def test_current_version_no_migration(self):
        data = add_schema_version({}, "worldview", CURRENT_VERSIONS["worldview"])
        assert needs_migration(data, "worldview") is False

    def test_old_version_needs_migration(self):
        data = add_schema_version({}, "worldview", "0.1.0")
        assert needs_migration(data, "worldview", "1.0.0") is True

    def test_newer_version_no_migration(self):
        data = add_schema_version({}, "worldview", "9.9.9")
        assert needs_migration(data, "worldview", "1.0.0") is False


class TestMigrate:
    """Test migrate function."""

    def test_already_at_target_version(self):
        data = add_schema_version({"key": "val"}, "worldview", "1.0.0")
        result = migrate(data, "worldview", "1.0.0")
        assert result is data  # Same object, no migration needed

    def test_no_migration_path_updates_version(self):
        data = add_schema_version({"key": "val"}, "memory", "0.5.0")
        result = migrate(data, "memory", "1.0.0")
        assert result["schema_version"]["version"] == "1.0.0"
        assert result["schema_version"]["migrated_from"] == "0.5.0"

    def test_worldview_v1_to_v2_migration(self):
        """Test the built-in worldview v1 -> v2 example migration."""
        data = add_schema_version(
            {"beliefs": [], "knowledge_gaps": ["gap1"]},
            "worldview",
            "1.0.0",
        )
        result = migrate(data, "worldview", "2.0.0")
        assert result["schema_version"]["version"] == "2.0.0"
        # Migration renames knowledge_gaps to gaps
        assert "gaps" in result
        assert result["gaps"] == ["gap1"]
        # synthesis_count added with default
        assert result["synthesis_count"] == 0


class TestEnsureVersioned:
    """Test ensure_versioned function."""

    def test_adds_version_if_missing(self):
        data = {"key": "value"}
        result = ensure_versioned(data, "trace")
        assert "schema_version" in result

    def test_preserves_existing_version(self):
        data = add_schema_version({"key": "value"}, "trace", "2.0.0")
        result = ensure_versioned(data, "trace")
        assert result["schema_version"]["version"] == "2.0.0"


class TestRegisterMigration:
    """Test register_migration decorator."""

    def test_registers_migration(self):
        @register_migration("test_type_register", "1.0.0", "2.0.0")
        def migrate_test(data):
            data["migrated"] = True
            return data

        assert ("test_type_register", "1.0.0", "2.0.0") in _migrations

        # Clean up
        del _migrations[("test_type_register", "1.0.0", "2.0.0")]


class TestGetMigrationPath:
    """Test get_migration_path function."""

    def test_direct_path(self):
        path = get_migration_path("worldview", "1.0.0", "2.0.0")
        assert path == [("1.0.0", "2.0.0")]

    def test_no_path(self):
        path = get_migration_path("nonexistent", "1.0.0", "5.0.0")
        assert path == []

    def test_multi_step_path(self):
        # Register temporary migrations
        @register_migration("test_multi", "1.0.0", "2.0.0")
        def m1(data):
            return data

        @register_migration("test_multi", "2.0.0", "3.0.0")
        def m2(data):
            return data

        path = get_migration_path("test_multi", "1.0.0", "3.0.0")
        assert path == [("1.0.0", "2.0.0"), ("2.0.0", "3.0.0")]

        # Clean up
        del _migrations[("test_multi", "1.0.0", "2.0.0")]
        del _migrations[("test_multi", "2.0.0", "3.0.0")]


class TestSaveLoadVersionedJson:
    """Test file I/O utilities."""

    def test_save_and_load(self, tmp_path):
        data = {"beliefs": ["test"], "count": 42}
        path = tmp_path / "test_data.json"

        save_versioned_json(data, path, "worldview")

        assert path.exists()
        loaded = load_versioned_json(path, "worldview", auto_migrate=False)
        assert loaded["beliefs"] == ["test"]
        assert loaded["count"] == 42
        assert "schema_version" in loaded

    def test_load_auto_migrates(self, tmp_path):
        # Save with old version (0.9.0 is below current 1.0.0)
        data = {"beliefs": [], "knowledge_gaps": ["gap"]}
        path = tmp_path / "test_migrate.json"
        save_versioned_json(data, path, "worldview", version="0.9.0")

        # Load with auto-migrate — version should be updated to current
        loaded = load_versioned_json(path, "worldview", auto_migrate=True)
        assert loaded["schema_version"]["version"] == CURRENT_VERSIONS["worldview"]
        assert loaded["schema_version"]["migrated_from"] == "0.9.0"

    def test_save_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "nested" / "dir" / "data.json"
        save_versioned_json({"key": "val"}, path, "trace")
        assert path.exists()

    def test_load_unversioned_adds_version(self, tmp_path):
        path = tmp_path / "unversioned.json"
        with open(path, "w") as f:
            json.dump({"raw": "data"}, f)

        loaded = load_versioned_json(path, "trace", auto_migrate=False)
        assert "schema_version" in loaded
        assert loaded["raw"] == "data"


class TestCurrentVersions:
    """Test CURRENT_VERSIONS constant."""

    def test_all_types_present(self):
        expected_types = [
            "worldview",
            "expert_profile",
            "conversation",
            "trace",
            "memory",
            "graph",
            "belief",
            "cost_record",
        ]
        for t in expected_types:
            assert t in CURRENT_VERSIONS

    def test_versions_are_valid_semver(self):
        for schema_type, version in CURRENT_VERSIONS.items():
            parts = version.split(".")
            assert len(parts) == 3, f"{schema_type} version {version} is not semver"
            for part in parts:
                int(part)  # Should not raise
