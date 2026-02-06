"""Tests for consolidated Settings class.

Requirements: 1.1 - Configuration Consolidation
"""

import json
import os
from unittest.mock import patch

import pytest

from deepr.core.settings import (
    TASK_MODEL_MAP,
    BudgetSettings,
    DatabaseType,
    DomainVelocity,
    ProviderSettings,
    ProviderType,
    ResearchMode,
    Settings,
    StorageSettings,
    StorageType,
    get_settings,
    load_config,
)


class TestProviderSettings:
    """Tests for ProviderSettings dataclass."""

    def test_default_values(self):
        """Test default values are set correctly."""
        provider = ProviderSettings(name="openai")
        assert provider.name == "openai"
        assert provider.api_key == ""
        assert provider.base_url is None
        assert provider.enabled is True
        assert provider.rate_limit == 60
        assert provider.timeout == 120

    def test_is_configured_with_api_key(self):
        """Test is_configured returns True when API key is set."""
        provider = ProviderSettings(name="openai", api_key="sk-test-key")
        assert provider.is_configured() is True

    def test_is_configured_without_api_key(self):
        """Test is_configured returns False when API key is missing."""
        provider = ProviderSettings(name="openai")
        assert provider.is_configured() is False

    def test_azure_is_configured_with_endpoint(self):
        """Test Azure provider requires endpoint."""
        provider = ProviderSettings(name="azure", api_key="azure-key", azure_endpoint="https://test.openai.azure.com")
        assert provider.is_configured() is True

    def test_azure_not_configured_without_endpoint(self):
        """Test Azure provider not configured without endpoint."""
        provider = ProviderSettings(name="azure", api_key="azure-key")
        assert provider.is_configured() is False

    def test_azure_managed_identity(self):
        """Test Azure with managed identity is configured."""
        provider = ProviderSettings(
            name="azure", azure_endpoint="https://test.openai.azure.com", azure_use_managed_identity=True
        )
        assert provider.is_configured() is True

    def test_to_dict_masks_api_key(self):
        """Test to_dict masks API key by default."""
        provider = ProviderSettings(name="openai", api_key="sk-secret-key")
        result = provider.to_dict()
        assert result["api_key"] == "***"

    def test_to_dict_shows_api_key(self):
        """Test to_dict can show API key when requested."""
        provider = ProviderSettings(name="openai", api_key="sk-secret-key")
        result = provider.to_dict(mask_keys=False)
        assert result["api_key"] == "sk-secret-key"


class TestStorageSettings:
    """Tests for StorageSettings dataclass."""

    def test_default_values(self):
        """Test default values."""
        storage = StorageSettings()
        assert storage.type == StorageType.LOCAL
        assert storage.local_path == "data/reports"
        assert storage.azure_container == "reports"

    def test_to_dict(self):
        """Test to_dict conversion."""
        storage = StorageSettings(azure_connection_string="secret-conn")
        result = storage.to_dict()
        assert result["type"] == "local"
        assert result["azure_connection_string"] == "***"


class TestBudgetSettings:
    """Tests for BudgetSettings dataclass."""

    def test_default_values(self):
        """Test default budget values."""
        budget = BudgetSettings()
        assert budget.max_cost_per_job == 5.0
        assert budget.daily_limit == 25.0
        assert budget.monthly_limit == 200.0

    def test_alert_thresholds(self):
        """Test alert threshold defaults."""
        budget = BudgetSettings()
        assert budget.alert_threshold_50 == 0.50
        assert budget.alert_threshold_80 == 0.80
        assert budget.alert_threshold_95 == 0.95


class TestSettings:
    """Tests for main Settings class."""

    @pytest.fixture(autouse=True)
    def reset_settings(self):
        """Reset Settings singleton before each test."""
        Settings.reset()
        yield
        Settings.reset()

    def test_default_values(self):
        """Test default settings values."""
        settings = Settings()
        assert settings.environment == "local"
        assert settings.debug is False
        assert settings.log_level == "INFO"
        assert settings.default_provider == "xai"
        assert settings.default_model == "grok-4-fast"
        assert settings.deep_research_provider == "openai"
        assert settings.deep_research_model == "o3-deep-research"

    def test_load_creates_singleton(self):
        """Test load() returns cached singleton."""
        settings1 = Settings.load()
        settings2 = Settings.load()
        assert settings1 is settings2

    def test_load_with_reset(self):
        """Test load() with reset creates new instance."""
        settings1 = Settings.load()
        settings2 = Settings.load(reset_singleton=True)
        assert settings1 is not settings2

    def test_load_with_cli_overrides(self):
        """Test CLI overrides are applied."""
        settings = Settings.load(cli_overrides={"default_provider": "azure", "debug": True})
        assert settings.default_provider == "azure"
        assert settings.debug is True
        assert settings._overrides["default_provider"] == "cli"

    @patch.dict(os.environ, {"DEEPR_DEFAULT_PROVIDER": "gemini"})
    def test_environment_variable_override(self):
        """Test environment variables override defaults."""
        settings = Settings.load(reset_singleton=True)
        assert settings.default_provider == "gemini"
        assert settings._overrides["default_provider"] == "env"

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key"})
    def test_provider_api_key_from_env(self):
        """Test provider API key loaded from environment."""
        settings = Settings.load(reset_singleton=True)
        assert "openai" in settings.providers
        assert settings.providers["openai"].api_key == "sk-test-key"

    @patch.dict(os.environ, {"XAI_API_KEY": "xai-test-key", "DEEPR_DEFAULT_PROVIDER": "xai"})
    def test_xai_provider_from_env(self):
        """Test XAI provider loaded from environment."""
        settings = Settings.load(reset_singleton=True)
        assert "xai" in settings.providers
        assert settings.providers["xai"].api_key == "xai-test-key"

    @patch.dict(os.environ, {"AZURE_OPENAI_KEY": "azure-key", "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com"})
    def test_azure_provider_from_env(self):
        """Test Azure provider loaded from environment."""
        settings = Settings.load(reset_singleton=True)
        assert "azure" in settings.providers
        assert settings.providers["azure"].api_key == "azure-key"
        assert settings.providers["azure"].azure_endpoint == "https://test.openai.azure.com"

    @patch.dict(
        os.environ, {"DEEPR_MAX_COST_PER_JOB": "10.0", "DEEPR_DAILY_LIMIT": "50.0", "DEEPR_MONTHLY_LIMIT": "500.0"}
    )
    def test_budget_settings_from_env(self):
        """Test budget settings loaded from environment."""
        settings = Settings.load(reset_singleton=True)
        assert settings.budget.max_cost_per_job == 10.0
        assert settings.budget.daily_limit == 50.0
        assert settings.budget.monthly_limit == 500.0

    @patch.dict(os.environ, {"DEEPR_STORAGE": "blob"})
    def test_storage_type_from_env(self):
        """Test storage type loaded from environment."""
        settings = Settings.load(reset_singleton=True)
        assert settings.storage.type == StorageType.BLOB

    @patch.dict(os.environ, {"DEEPR_DATABASE_TYPE": "sqlite"})
    def test_database_type_from_env(self):
        """Test database type loaded from environment."""
        settings = Settings.load(reset_singleton=True)
        assert settings.database.type == DatabaseType.SQLITE

    def test_get_method(self):
        """Test get() method for nested values."""
        settings = Settings()
        assert settings.get("budget.daily_limit") == 25.0
        assert settings.get("research.max_wait_time") == 1800
        assert settings.get("nonexistent", "default") == "default"

    def test_get_provider(self):
        """Test get_provider() method."""
        settings = Settings()
        settings.providers["openai"] = ProviderSettings(name="openai", api_key="test")

        provider = settings.get_provider("openai")
        assert provider is not None
        assert provider.name == "openai"

        # Default provider
        settings.default_provider = "openai"
        provider = settings.get_provider()
        assert provider.name == "openai"

    def test_get_api_key(self):
        """Test get_api_key() method."""
        settings = Settings()
        settings.providers["openai"] = ProviderSettings(name="openai", api_key="sk-test")

        assert settings.get_api_key("openai") == "sk-test"
        assert settings.get_api_key("nonexistent") == ""

    def test_get_model_for_task(self):
        """Test get_model_for_task() returns correct provider/model."""
        settings = Settings()

        provider, model = settings.get_model_for_task("deep_research")
        assert provider == "openai"
        assert model == "o3-deep-research"

        provider, model = settings.get_model_for_task("quick_lookup")
        assert provider == "xai"
        assert model == "grok-4-fast"

    def test_get_model_for_unknown_task(self):
        """Test get_model_for_task() falls back to defaults."""
        settings = Settings()
        settings.default_provider = "test"
        settings.default_model = "test-model"

        provider, model = settings.get_model_for_task("unknown_task")
        assert provider == "test"
        assert model == "test-model"

    def test_validate_missing_provider(self):
        """Test validate() catches missing provider config."""
        settings = Settings()
        settings.default_provider = "nonexistent"
        settings.providers = {}

        errors = settings.validate()
        assert any("not configured" in err for err in errors)

    def test_validate_missing_api_key(self):
        """Test validate() catches missing API key."""
        settings = Settings()
        settings.default_provider = "openai"
        settings.providers["openai"] = ProviderSettings(name="openai")

        errors = settings.validate()
        assert any("No API key" in err for err in errors)

    def test_validate_invalid_budget(self):
        """Test validate() catches invalid budget limits."""
        settings = Settings()
        settings.providers["xai"] = ProviderSettings(name="xai", api_key="test")
        settings.budget.daily_limit = 0

        errors = settings.validate()
        assert any("Daily budget" in err for err in errors)

    def test_to_dict(self):
        """Test to_dict() serialization."""
        settings = Settings()
        settings.providers["openai"] = ProviderSettings(name="openai", api_key="secret")

        result = settings.to_dict()
        assert result["default_provider"] == "xai"
        assert result["providers"]["openai"]["api_key"] == "***"

    def test_to_dict_unmask(self):
        """Test to_dict() with unmasked keys."""
        settings = Settings()
        settings.providers["openai"] = ProviderSettings(name="openai", api_key="secret")

        result = settings.to_dict(mask_keys=False)
        assert result["providers"]["openai"]["api_key"] == "secret"

    def test_show(self):
        """Test show() generates readable output."""
        settings = Settings()
        settings.providers["openai"] = ProviderSettings(name="openai", api_key="secret")

        output = settings.show()
        assert "Deepr Configuration" in output
        assert "default_provider" in output.lower() or "Default Provider" in output
        assert "***" in output  # API key should be masked


class TestConfigFile:
    """Tests for config file loading."""

    @pytest.fixture(autouse=True)
    def reset_settings(self):
        """Reset Settings singleton before each test."""
        Settings.reset()
        yield
        Settings.reset()

    def test_load_json_config(self, tmp_path):
        """Test loading JSON config file."""
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps(
                {"default_provider": "anthropic", "default_model": "claude-3-opus", "budget": {"daily_limit": 100.0}}
            )
        )

        settings = Settings.load(config_path=config_file)
        assert settings.default_provider == "anthropic"
        assert settings.default_model == "claude-3-opus"
        assert settings.budget.daily_limit == 100.0

    def test_load_yaml_config(self, tmp_path):
        """Test loading YAML config file."""
        pytest.importorskip("yaml")

        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
default_provider: gemini
budget:
  daily_limit: 75.0
  monthly_limit: 750.0
""")

        settings = Settings.load(config_path=config_file)
        assert settings.default_provider == "gemini"
        assert settings.budget.daily_limit == 75.0
        assert settings.budget.monthly_limit == 750.0

    @patch.dict(os.environ, {}, clear=False)
    def test_config_file_with_providers(self, tmp_path):
        """Test loading providers from config file."""
        # Remove OPENAI_API_KEY from env if present so file value is used
        env_backup = os.environ.pop("OPENAI_API_KEY", None)
        try:
            config_file = tmp_path / "config.json"
            config_file.write_text(
                json.dumps(
                    {
                        "providers": {
                            "custom_provider": {"api_key": "sk-from-file", "default_model": "gpt-4", "rate_limit": 30}
                        }
                    }
                )
            )

            settings = Settings.load(config_path=config_file, reset_singleton=True)
            assert "custom_provider" in settings.providers
            assert settings.providers["custom_provider"].api_key == "sk-from-file"
            assert settings.providers["custom_provider"].rate_limit == 30
        finally:
            if env_backup:
                os.environ["OPENAI_API_KEY"] = env_backup


class TestLegacyCompatibility:
    """Tests for legacy compatibility functions."""

    @pytest.fixture(autouse=True)
    def reset_settings(self):
        """Reset Settings singleton before each test."""
        Settings.reset()
        yield
        Settings.reset()

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-legacy-test"})
    def test_load_config_returns_dict(self):
        """Test load_config() returns legacy format dictionary."""
        config = load_config()

        assert isinstance(config, dict)
        assert "provider" in config
        assert "api_key" in config
        assert "storage" in config
        assert "results_dir" in config
        assert "max_cost_per_job" in config
        assert "max_daily_cost" in config
        assert "max_monthly_cost" in config

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-legacy-test"})
    def test_get_settings_function(self):
        """Test get_settings() function returns Settings instance."""
        settings = get_settings()

        assert isinstance(settings, Settings)
        assert settings.get_api_key("openai") == "sk-legacy-test"

    def test_get_settings_with_overrides(self):
        """Test get_settings() with CLI overrides."""
        settings = get_settings(cli_overrides={"debug": True})
        assert settings.debug is True


class TestTaskModelMap:
    """Tests for task-to-model mapping."""

    def test_task_model_map_entries(self):
        """Test TASK_MODEL_MAP has expected entries."""
        assert "quick_lookup" in TASK_MODEL_MAP
        assert "deep_research" in TASK_MODEL_MAP
        assert "synthesis" in TASK_MODEL_MAP
        assert "chat" in TASK_MODEL_MAP

    def test_task_model_map_values(self):
        """Test TASK_MODEL_MAP returns tuples."""
        for task, value in TASK_MODEL_MAP.items():
            assert isinstance(value, tuple)
            assert len(value) == 2
            provider, model = value
            assert isinstance(provider, str)
            assert isinstance(model, str)


class TestEnums:
    """Tests for configuration enums."""

    def test_provider_type_values(self):
        """Test ProviderType enum values."""
        assert ProviderType.OPENAI.value == "openai"
        assert ProviderType.AZURE.value == "azure"
        assert ProviderType.GEMINI.value == "gemini"
        assert ProviderType.GROK.value == "grok"

    def test_storage_type_values(self):
        """Test StorageType enum values."""
        assert StorageType.LOCAL.value == "local"
        assert StorageType.BLOB.value == "blob"

    def test_database_type_values(self):
        """Test DatabaseType enum values."""
        assert DatabaseType.JSONL.value == "jsonl"
        assert DatabaseType.SQLITE.value == "sqlite"
        assert DatabaseType.COSMOSDB.value == "cosmosdb"

    def test_research_mode_values(self):
        """Test ResearchMode enum values."""
        assert ResearchMode.READ_ONLY.value == "read_only"
        assert ResearchMode.STANDARD.value == "standard"
        assert ResearchMode.EXTENDED.value == "extended"
        assert ResearchMode.UNRESTRICTED.value == "unrestricted"

    def test_domain_velocity_values(self):
        """Test DomainVelocity enum values."""
        assert DomainVelocity.SLOW.value == "slow"
        assert DomainVelocity.MEDIUM.value == "medium"
        assert DomainVelocity.FAST.value == "fast"
