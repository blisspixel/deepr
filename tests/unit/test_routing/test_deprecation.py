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
        assert entry.new_model == "gpt-5.6-sol"
        assert entry.sunset_date == "2026-07-23"

    def test_grok3_deprecated(self):
        entry = check_deprecation("grok-3")
        assert entry is not None
        assert entry.new_model == "xai/grok-4-3"

    def test_gpt4o_deprecated(self):
        entry = check_deprecation("gpt-4o")
        assert entry is not None
        assert entry.new_model == "gpt-5.6-terra"
        assert entry.sunset_date == "2027-01-14"
        assert entry.auto_migrate is False
        assert "gpt-6-luna" in entry.warning
        assert "preview-only" in entry.warning

    def test_gpt4o_mini_deprecated(self):
        entry = check_deprecation("gpt-4o-mini")
        assert entry is not None
        assert entry.new_model == "gpt-5.6-luna"
        assert entry.sunset_date == "2027-01-14"
        assert entry.auto_migrate is False

    def test_current_model_not_deprecated(self):
        assert check_deprecation("gpt-5.4") is None
        assert check_deprecation("gpt-5.6-sol") is None
        assert check_deprecation("gpt-5.6-terra") is None
        assert check_deprecation("grok-4.20-0309-reasoning") is None
        assert check_deprecation("gemini-3.1-pro-preview") is None
        assert check_deprecation("gemini-4-argon") is None
        assert check_deprecation("gemini-3.8-flash") is None

    def test_shutdown_gemini_previews_are_deprecated(self):
        pro = check_deprecation("gemini-3-pro-preview")
        flash_lite = check_deprecation("gemini-3.1-flash-lite-preview")
        research = check_deprecation("deep-research-pro-preview-12-2025")

        assert pro is not None
        assert pro.new_model == "gemini-4-argon"
        assert pro.sunset_date == "2026-03-09"
        assert flash_lite is not None
        assert flash_lite.new_model == "gemini-3.5-flash-lite"
        assert research is not None
        assert research.new_model == "deep-research-max-preview-04-2026"
        assert research.sunset_date == "2026-10-23"

    def test_versioned_gpt4o_mini_matches_correctly(self):
        """gpt-4o-mini-2024-08-06 should match gpt-4o-mini, NOT gpt-4o."""
        entry = check_deprecation("gpt-4o-mini-2024-08-06")
        assert entry is not None
        assert entry.old_model == "gpt-4o-mini"
        assert entry.new_model == "gpt-5.6-luna"  # NOT the gpt-4o successor

    def test_versioned_gpt4o_matches_correctly(self):
        """gpt-4o-2024-08-06 should match gpt-4o."""
        entry = check_deprecation("gpt-4o-2024-08-06")
        assert entry is not None
        assert entry.new_model == "gpt-5.6-terra"
        assert entry.sunset_date == "2027-01-14"

    def test_unknown_model(self):
        assert check_deprecation("totally-fake-model") is None

    def test_registry_has_entries(self):
        assert len(DEPRECATION_REGISTRY) > 0


class TestMigrateModel:
    def test_deprecated_auto_migrates(self):
        model, confidence, warning = migrate_model("o3-deep-research")
        assert model == "gpt-5.6-sol"
        assert confidence == 1.0
        assert warning is not None
        assert "2026-07-23" in warning

    def test_grok3_auto_migrates(self):
        model, confidence, warning = migrate_model("grok-3")
        # Provider prefix is stripped - downstream provider clients
        # consume the plain model id, not "<provider>/<model>".
        assert model == "grok-4-3"
        assert confidence == 1.0
        assert warning is not None

    def test_current_model_unchanged(self):
        model, confidence, warning = migrate_model("gpt-5.4")
        assert model == "gpt-5.4"
        assert confidence == 1.0
        assert warning is None

    def test_gpt4o_keeps_explicit_identity_with_warning(self):
        """Retiring OpenAI ids warn but never silently become another priced model."""
        model, confidence, warning = migrate_model("gpt-4o")
        assert model == "gpt-4o"
        assert confidence == 1.0
        assert warning is not None
        assert "2027-01-14" in warning

    def test_unknown_model_passes_through(self):
        model, confidence, warning = migrate_model("custom-model-v7")
        assert model == "custom-model-v7"
        assert confidence == 1.0
        assert warning is None

    def test_confidence_preserved(self):
        model, confidence, warning = migrate_model("grok-3", confidence=0.75)
        # Provider prefix is stripped - downstream provider clients
        # consume the plain model id, not "<provider>/<model>".
        assert model == "grok-4-3"
        assert confidence == 0.75
        assert warning is not None

    def test_shutdown_gemini_preview_migrates(self):
        model, confidence, warning = migrate_model("gemini-3.1-flash-lite-preview")

        assert model == "gemini-3.5-flash-lite"
        assert confidence == 1.0
        assert warning is not None


class TestRetiredOpenAIDefaults:
    """Issue 213: shut-down research ids warn, and defaults do not select them.

    Shutdown dates are from the OpenAI deprecations page checked 2026-10-12:
    o3-deep-research* and o4-mini-deep-research* on 2026-07-23 (gpt-5.6-sol),
    o4-mini* on 2026-10-23 (gpt-5.6-terra).
    """

    DEEP_RESEARCH_IDS = (
        "o3-deep-research",
        "o3-deep-research-2025-06-26",
        "o4-mini-deep-research",
        "o4-mini-deep-research-2025-06-26",
    )
    O4_MINI_IDS = ("o4-mini", "o4-mini-2025-04-16")

    def test_retired_deep_research_ids_carry_sunset_and_successor(self):
        for model_id in self.DEEP_RESEARCH_IDS:
            entry = check_deprecation(model_id)
            assert entry is not None, model_id
            assert entry.sunset_date == "2026-07-23", model_id
            assert entry.new_model == "gpt-5.6-sol", model_id

    def test_o4_mini_shutdown_keeps_explicit_identity(self):
        assert migrate_model("o4-mini")[0] == "o4-mini"

    def test_o4_mini_carries_sunset_and_successor(self):
        for model_id in self.O4_MINI_IDS:
            entry = check_deprecation(model_id)
            assert entry is not None, model_id
            assert entry.sunset_date == "2026-10-23", model_id
            assert entry.new_model == "gpt-5.6-terra", model_id

    def test_dated_deep_research_snapshot_does_not_match_o4_mini(self):
        entry = check_deprecation("o4-mini-deep-research-2025-06-26")
        assert entry is not None
        assert entry.old_model == "o4-mini-deep-research"

    def test_default_deep_research_model_is_not_retired(self, monkeypatch):
        from deepr.cli.commands.research_support import resolve_research_route
        from deepr.config import AppConfig, ProviderConfig
        from deepr.core.costs import CostEstimator
        from deepr.core.settings import TASK_MODEL_MAP, Settings

        for name in (
            "DEEPR_DEEP_RESEARCH_MODEL",
            "DEEPR_DEEP_RESEARCH_PROVIDER",
            "DEEPR_DEFAULT_MODEL",
            "DEEPR_DEFAULT_PROVIDER",
            "AZURE_DEPLOYMENT_O3",
            "AZURE_DEPLOYMENT_O4_MINI",
            "AZURE_DEPLOYMENT_GPT56_SOL",
            "AZURE_DEPLOYMENT_GPT56_TERRA",
        ):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("DEEPR_USE_BENCHMARK_ROUTING", "false")

        provider_config = ProviderConfig()
        settings = Settings()
        defaults = {
            provider_config.deep_research_model,
            provider_config.TASK_MODEL_MAP["deep_research"][1],
            provider_config.azure_foundry_deep_research_deployment,
            settings.deep_research_model,
            TASK_MODEL_MAP["deep_research"][1],
            resolve_research_route(None, None)[1],
            CostEstimator.estimate_cost("Hi").model,
        }
        assert defaults == {"gpt-5.6-sol"}
        for model_id in defaults:
            entry = check_deprecation(model_id)
            assert entry is None or entry.sunset_date == ""

        app = AppConfig.from_env()
        assert app.provider.deep_research_model == "gpt-5.6-sol"
        assert app.provider.model_mappings["gpt-5.6-sol"] == "gpt-5.6-sol"
        assert app.provider.model_mappings["gpt-5.6-terra"] == "gpt-5.6-terra"
        assert app.provider.default_model == "gpt-5.6-sol"

    def test_successor_web_search_stays_inside_the_reserved_input_ceiling(self):
        from deepr.cli.commands.research_support import bounded_tool_disable_flags
        from deepr.services.research_bounds import builtin_web_search_reservable

        assert builtin_web_search_reservable("gpt-5.6-sol") is False
        assert builtin_web_search_reservable("gpt-5.6-terra") is False
        assert builtin_web_search_reservable("o3-deep-research") is True
        assert builtin_web_search_reservable("o4-mini-deep-research") is True
        assert bounded_tool_disable_flags("openai", False, False, "gpt-5.6-sol") == (True, True)
        assert bounded_tool_disable_flags("openai", False, False, "o3-deep-research") == (False, True)


class TestOpenAILifecycle20261027:
    """OpenAI deprecations page checked 2026-10-27 (docs/design/model-lifecycle-2026-10-27.md)."""

    EXPECTED = {
        "gpt-4.1-nano": ("2026-10-23", "gpt-5.6-luna"),
        "o4-mini": ("2026-10-23", "gpt-5.6-terra"),
        "o3-mini": ("2026-10-23", "gpt-5.6-terra"),
        "gpt-4o-2024-05-13": ("2026-10-23", "gpt-5.6-terra"),
        "o3": ("2026-12-11", "gpt-5.6-sol"),
        "o3-2025-04-16": ("2026-12-11", "gpt-5.6-sol"),
        "gpt-5": ("2026-12-11", "gpt-5.6-sol"),
        "gpt-5-mini": ("2026-12-11", "gpt-5.6-terra"),
        "gpt-5-nano": ("2026-12-11", "gpt-5.6-luna"),
        "gpt-4o": ("2027-01-14", "gpt-5.6-terra"),
        "gpt-4o-2024-08-06": ("2027-01-14", "gpt-5.6-terra"),
        "gpt-4o-2024-11-20": ("2027-01-14", "gpt-5.6-terra"),
        "gpt-4o-mini": ("2027-01-14", "gpt-5.6-luna"),
        "gpt-4o-mini-2024-07-18": ("2027-01-14", "gpt-5.6-luna"),
        "gpt-4.1": ("2027-01-14", "gpt-5.6-terra"),
        "gpt-4.1-2025-04-14": ("2027-01-14", "gpt-5.6-terra"),
        "gpt-4.1-mini": ("2027-01-14", "gpt-5.6-luna"),
        "gpt-4.1-mini-2025-04-14": ("2027-01-14", "gpt-5.6-luna"),
    }

    def test_dates_and_successors(self):
        for model_id, (sunset, successor) in self.EXPECTED.items():
            entry = check_deprecation(model_id)
            assert entry is not None, model_id
            assert (entry.sunset_date, entry.new_model) == (sunset, successor), model_id

    def test_longer_keys_win_over_family_prefix(self):
        assert check_deprecation("gpt-4.1-nano-2025-04-14").old_model == "gpt-4.1-nano"
        assert check_deprecation("gpt-4.1-mini-2025-04-14").old_model == "gpt-4.1-mini"
        assert check_deprecation("o3-mini-2025-01-31").old_model == "o3-mini"

    def test_o3_date_does_not_leak_to_other_o3_family_ids(self):
        assert check_deprecation("o3-pro") is None

    def test_openai_entries_never_auto_migrate(self):
        for model_id in self.EXPECTED:
            model, _, warning = migrate_model(model_id)
            assert model == model_id
            assert warning

    def test_validated_successors_and_preview_candidates_are_not_retired(self):
        for model_id in ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-6-luna", "gpt-5.2", "gpt-5.4-nano"):
            assert check_deprecation(model_id) is None, model_id

    def test_shutdown_follows_recorded_dates(self):
        from datetime import date

        from deepr.routing.deprecation import is_shutdown

        assert is_shutdown("gpt-4.1-nano", today=date(2026, 10, 23))
        assert is_shutdown("gpt-4o-2024-05-13", today=date(2026, 10, 27))
        assert not is_shutdown("gpt-4o-2024-08-06", today=date(2026, 10, 27))
        assert not is_shutdown("o3", today=date(2026, 12, 10))
        assert is_shutdown("o3", today=date(2026, 12, 11))
        assert not is_shutdown("gpt-4.1-mini", today=date(2027, 1, 13))
        assert is_shutdown("gpt-4.1-mini", today=date(2027, 1, 14))
