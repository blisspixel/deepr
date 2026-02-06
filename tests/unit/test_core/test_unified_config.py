"""Tests for core unified configuration management."""

import os
from pathlib import Path
from unittest.mock import patch

from deepr.core.unified_config import ProviderConfig, UnifiedConfig


class TestProviderConfig:
    """Test ProviderConfig dataclass."""

    def test_defaults(self):
        pc = ProviderConfig(name="openai")
        assert pc.name == "openai"
        assert pc.api_key == ""
        assert pc.default_model == ""
        assert pc.enabled is True
        assert pc.rate_limit == 60
        assert pc.timeout == 120

    def test_to_dict_masks_keys(self):
        pc = ProviderConfig(name="openai", api_key="sk-secret-key")
        d = pc.to_dict(mask_keys=True)
        assert d["api_key"] == "***"
        assert d["name"] == "openai"

    def test_to_dict_shows_keys(self):
        pc = ProviderConfig(name="openai", api_key="sk-secret-key")
        d = pc.to_dict(mask_keys=False)
        assert d["api_key"] == "sk-secret-key"

    def test_to_dict_empty_key_not_masked(self):
        pc = ProviderConfig(name="openai", api_key="")
        d = pc.to_dict(mask_keys=True)
        assert d["api_key"] == ""


class TestUnifiedConfig:
    """Test UnifiedConfig dataclass and loading."""

    def test_defaults(self):
        config = UnifiedConfig()
        assert config.default_provider == "openai"
        assert config.default_model == "gpt-4o"
        assert config.data_dir == "data"
        assert config.log_level == "INFO"
        assert config.providers == {}

    def test_expert_defaults(self):
        config = UnifiedConfig()
        assert config.expert_defaults["monthly_learning_budget"] == 5.0
        assert config.expert_defaults["staleness_threshold_days"] == 90
        assert config.expert_defaults["max_context_tokens"] == 8000

    def test_research_defaults(self):
        config = UnifiedConfig()
        assert config.research_defaults["max_rounds"] == 5
        assert config.research_defaults["default_budget"] == 1.0

    def test_budget_limits(self):
        config = UnifiedConfig()
        assert config.budget_limits["daily_limit"] == 10.0
        assert config.budget_limits["monthly_limit"] == 100.0


class TestUnifiedConfigGet:
    """Test the get() method for nested access."""

    def test_get_simple_field(self):
        config = UnifiedConfig()
        assert config.get("default_provider") == "openai"

    def test_get_nested_field(self):
        config = UnifiedConfig()
        assert config.get("budget_limits.daily_limit") == 10.0

    def test_get_missing_returns_default(self):
        config = UnifiedConfig()
        assert config.get("nonexistent", "fallback") == "fallback"

    def test_get_nested_missing_returns_default(self):
        config = UnifiedConfig()
        assert config.get("budget_limits.nonexistent") is None

    def test_get_provider_config(self):
        config = UnifiedConfig()
        config.providers["openai"] = ProviderConfig(name="openai", api_key="sk-test")
        pc = config.get_provider_config("openai")
        assert pc is not None
        assert pc.api_key == "sk-test"

    def test_get_provider_config_missing(self):
        config = UnifiedConfig()
        assert config.get_provider_config("nonexistent") is None

    def test_get_api_key(self):
        config = UnifiedConfig()
        config.providers["openai"] = ProviderConfig(name="openai", api_key="sk-test")
        assert config.get_api_key("openai") == "sk-test"

    def test_get_api_key_missing(self):
        config = UnifiedConfig()
        assert config.get_api_key("nonexistent") == ""


class TestUnifiedConfigApplyEnv:
    """Test environment variable application."""

    def test_apply_env_provider(self):
        config = UnifiedConfig()
        with patch.dict(os.environ, {"DEEPR_PROVIDER": "anthropic"}, clear=False):
            config._apply_env()
        assert config.default_provider == "anthropic"

    def test_apply_env_model(self):
        config = UnifiedConfig()
        with patch.dict(os.environ, {"DEEPR_MODEL": "claude-3"}, clear=False):
            config._apply_env()
        assert config.default_model == "claude-3"

    def test_apply_env_api_key(self):
        config = UnifiedConfig()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-env-key"}, clear=False):
            config._apply_env()
        assert "openai" in config.providers
        assert config.providers["openai"].api_key == "sk-env-key"

    def test_apply_env_multiple_providers(self):
        config = UnifiedConfig()
        env = {
            "OPENAI_API_KEY": "sk-openai",
            "ANTHROPIC_API_KEY": "sk-anthropic",
            "XAI_API_KEY": "xai-key",
        }
        with patch.dict(os.environ, env, clear=False):
            config._apply_env()
        assert config.providers["openai"].api_key == "sk-openai"
        assert config.providers["anthropic"].api_key == "sk-anthropic"
        assert config.providers["grok"].api_key == "xai-key"

    def test_apply_env_budget_limits(self):
        config = UnifiedConfig()
        with patch.dict(os.environ, {"DEEPR_DAILY_LIMIT": "25.0"}, clear=False):
            config._apply_env()
        assert config.budget_limits["daily_limit"] == 25.0


class TestUnifiedConfigApplyCli:
    """Test CLI override application."""

    def test_apply_cli_simple(self):
        config = UnifiedConfig()
        config._apply_cli({"default_model": "gpt-5"})
        assert config.default_model == "gpt-5"

    def test_apply_cli_nested(self):
        config = UnifiedConfig()
        config._apply_cli({"budget_limits.daily_limit": "50.0"})
        assert config.budget_limits["daily_limit"] == 50.0

    def test_apply_cli_none_ignored(self):
        config = UnifiedConfig()
        config._apply_cli({"default_model": None, "log_level": "DEBUG"})
        assert config.default_model == "gpt-4o"  # Unchanged
        assert config.log_level == "DEBUG"


class TestUnifiedConfigApplyDict:
    """Test dictionary configuration application."""

    def test_simple_fields(self):
        config = UnifiedConfig()
        config._apply_dict(
            {"default_provider": "gemini", "log_level": "DEBUG"},
            source="test",
        )
        assert config.default_provider == "gemini"
        assert config.log_level == "DEBUG"

    def test_providers(self):
        config = UnifiedConfig()
        config._apply_dict(
            {
                "providers": {
                    "openai": {
                        "api_key": "sk-test",
                        "default_model": "gpt-4o",
                        "enabled": True,
                    }
                }
            },
            source="test",
        )
        assert "openai" in config.providers
        assert config.providers["openai"].api_key == "sk-test"

    def test_expert_defaults_merge(self):
        config = UnifiedConfig()
        config._apply_dict(
            {"expert_defaults": {"staleness_threshold_days": 30}},
            source="test",
        )
        # Should merge, not replace
        assert config.expert_defaults["staleness_threshold_days"] == 30
        assert config.expert_defaults["monthly_learning_budget"] == 5.0


class TestUnifiedConfigApplyFile:
    """Test file-based configuration loading."""

    def test_json_config_file(self, tmp_path):
        config_file = tmp_path / "config.json"
        import json

        config_data = {
            "default_provider": "anthropic",
            "default_model": "claude-opus",
        }
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        config = UnifiedConfig()
        config._apply_file(config_file)
        assert config.default_provider == "anthropic"
        assert config.default_model == "claude-opus"

    def test_missing_config_file(self):
        config = UnifiedConfig()
        config._apply_file(Path("/nonexistent/path/config.json"))
        # Should not raise, just no changes
        assert config.default_provider == "openai"

    def test_none_config_path_searches_defaults(self):
        config = UnifiedConfig()
        # Should not raise even if no default config exists
        config._apply_file(None)


class TestUnifiedConfigLoad:
    """Test the load() classmethod."""

    def test_load_default(self):
        config = UnifiedConfig.load()
        assert isinstance(config, UnifiedConfig)
        assert config.default_provider == "openai"

    def test_load_with_cli_overrides(self):
        config = UnifiedConfig.load(cli_overrides={"default_model": "custom-model"})
        assert config.default_model == "custom-model"


class TestUnifiedConfigValidate:
    """Test validate() method."""

    def test_validates_missing_provider(self):
        config = UnifiedConfig()
        config.default_provider = "nonexistent"
        errors = config.validate()
        assert any("nonexistent" in e for e in errors)

    def test_validates_missing_api_key(self):
        config = UnifiedConfig()
        config.providers["openai"] = ProviderConfig(name="openai", api_key="")
        errors = config.validate()
        assert any("API key" in e for e in errors)

    def test_validates_negative_budget(self):
        config = UnifiedConfig()
        config.budget_limits["daily_limit"] = -1
        errors = config.validate()
        assert any("Daily budget" in e for e in errors)


class TestUnifiedConfigToDict:
    """Test to_dict() method."""

    def test_to_dict_structure(self):
        config = UnifiedConfig()
        d = config.to_dict()
        assert "default_provider" in d
        assert "default_model" in d
        assert "providers" in d
        assert "expert_defaults" in d
        assert "research_defaults" in d
        assert "budget_limits" in d
        assert "_source" in d

    def test_to_dict_masks_keys_by_default(self):
        config = UnifiedConfig()
        config.providers["openai"] = ProviderConfig(name="openai", api_key="sk-secret")
        d = config.to_dict(mask_keys=True)
        assert d["providers"]["openai"]["api_key"] == "***"


class TestUnifiedConfigShow:
    """Test show() method."""

    def test_show_returns_string(self):
        config = UnifiedConfig()
        result = config.show()
        assert isinstance(result, str)
        assert "Deepr Configuration" in result
        assert "Provider: openai" in result

    def test_show_includes_providers(self):
        config = UnifiedConfig()
        config.providers["openai"] = ProviderConfig(name="openai", api_key="sk-test")
        result = config.show()
        assert "openai:" in result
        assert "***" in result  # Key should be masked

    def test_show_includes_budget(self):
        config = UnifiedConfig()
        result = config.show()
        assert "Budget Limits:" in result
        assert "$10.00" in result


class TestUnifiedConfigSetNested:
    """Test _set_nested method."""

    def test_set_simple(self):
        config = UnifiedConfig()
        config._set_nested("log_level", "DEBUG")
        assert config.log_level == "DEBUG"

    def test_set_nested_dict(self):
        config = UnifiedConfig()
        config._set_nested("budget_limits.daily_limit", "25.0")
        assert config.budget_limits["daily_limit"] == 25.0

    def test_set_nonexistent_field_ignored(self):
        config = UnifiedConfig()
        config._set_nested("nonexistent_field", "value")
        assert not hasattr(config, "nonexistent_field") or getattr(config, "nonexistent_field", None) != "value"

    def test_set_float_conversion(self):
        config = UnifiedConfig()
        config._set_nested("budget_limits.monthly_limit", "200.0")
        assert config.budget_limits["monthly_limit"] == 200.0
        assert isinstance(config.budget_limits["monthly_limit"], float)


class TestUnifiedConfigFromAppConfig:
    """Test from_app_config classmethod."""

    def test_from_minimal_app_config(self):
        class MockAppConfig:
            log_level = "DEBUG"

        config = UnifiedConfig.from_app_config(MockAppConfig())
        assert config.log_level == "DEBUG"
        assert config._source == "AppConfig"

    def test_from_app_config_with_provider(self):
        class MockProvider:
            default_provider = "anthropic"
            default_model = "claude-3"
            openai_api_key = "sk-test"
            azure_api_key = None

        class MockAppConfig:
            provider = MockProvider()
            log_level = "INFO"

        config = UnifiedConfig.from_app_config(MockAppConfig())
        assert config.default_provider == "anthropic"
        assert config.default_model == "claude-3"
        assert "openai" in config.providers
        assert config.providers["openai"].api_key == "sk-test"

    def test_from_app_config_with_storage(self):
        class MockStorage:
            local_path = "/custom/data"

        class MockAppConfig:
            storage = MockStorage()
            log_level = "INFO"

        config = UnifiedConfig.from_app_config(MockAppConfig())
        assert config.data_dir == "/custom/data"
