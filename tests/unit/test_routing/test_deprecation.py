"""Tests for model deprecation registry and migration."""

from deepr.routing.deprecation import (
    DEPRECATION_REGISTRY,
    check_deprecation,
    migrate_model,
)


class TestCheckDeprecation:
    def test_exact_match(self):
        entry = check_deprecation("o3-deep-research")
        assert entry is not None
        assert entry.new_model == "o3-deep-research-2025-06-26"

    def test_grok3_deprecated(self):
        entry = check_deprecation("grok-3")
        assert entry is not None
        assert "4.20" in entry.new_model

    def test_gpt4o_deprecated(self):
        entry = check_deprecation("gpt-4o")
        assert entry is not None
        assert entry.new_model == "gpt-4.1"

    def test_gpt4o_mini_deprecated(self):
        entry = check_deprecation("gpt-4o-mini")
        assert entry is not None
        assert entry.new_model == "gpt-4.1-mini"

    def test_current_model_not_deprecated(self):
        assert check_deprecation("gpt-5.4") is None
        assert check_deprecation("o4-mini-deep-research") is None
        assert check_deprecation("grok-4.20-0309-reasoning") is None

    def test_unknown_model(self):
        assert check_deprecation("totally-fake-model") is None

    def test_registry_has_entries(self):
        assert len(DEPRECATION_REGISTRY) > 0


class TestMigrateModel:
    def test_deprecated_auto_migrates(self):
        model, warning = migrate_model("o3-deep-research")
        assert model == "o3-deep-research-2025-06-26"
        assert warning is not None
        assert "removing" in warning.lower() or "alias" in warning.lower()

    def test_grok3_auto_migrates(self):
        model, warning = migrate_model("grok-3")
        assert model == "grok-4.20-0309-reasoning"
        assert warning is not None

    def test_current_model_unchanged(self):
        model, warning = migrate_model("gpt-5.4")
        assert model == "gpt-5.4"
        assert warning is None

    def test_gpt4o_migrates_to_gpt41(self):
        model, warning = migrate_model("gpt-4o")
        assert model == "gpt-4.1"
        assert warning is not None

    def test_unknown_model_passes_through(self):
        model, warning = migrate_model("custom-model-v7")
        assert model == "custom-model-v7"
        assert warning is None
