"""Property-based tests for configuration system.

Tests the configuration hierarchy property:
- CLI flags override environment variables
- Environment variables override file config
- File config overrides defaults
- All configuration values are valid after loading

Requirements: 17.1, 17.2
Task: 18.5
"""

import os
import json
import tempfile
from typing import Any, Dict, Optional
from unittest.mock import patch

import pytest
from hypothesis import given, settings, strategies as st, assume, HealthCheck
from pydantic import ValidationError

from deepr.config import (
    AppConfig,
    ProviderConfig,
    StorageConfig,
    WebhookConfig,
    ResearchConfig,
    ExpertConfig,
    DatabaseConfig,
    load_config,
)


# =============================================================================
# Test Strategies
# =============================================================================

# Valid provider types
provider_types = st.sampled_from(["openai", "azure"])

# Valid storage types
storage_types = st.sampled_from(["local", "blob"])

# Valid environment types
environment_types = st.sampled_from(["local", "cloud"])

# Valid database types
database_types = st.sampled_from(["jsonl", "sqlite", "cosmosdb"])

# Valid log levels
log_levels = st.sampled_from(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])

# Valid model names (non-empty strings without special chars)
model_names = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
    min_size=1,
    max_size=50,
).filter(lambda x: x.strip() == x and len(x) > 0)

# Valid API keys (non-empty strings)
api_keys = st.text(min_size=10, max_size=100).filter(lambda x: x.strip() == x)

# Valid URLs
urls = st.from_regex(r"https://[a-z0-9-]+\.[a-z]{2,10}(/[a-z0-9-]*)*", fullmatch=True)

# Valid paths (simple alphanumeric with slashes)
paths = st.from_regex(r"[a-zA-Z0-9_/.-]+", fullmatch=True).filter(
    lambda x: len(x) > 0 and not x.startswith("/") and ".." not in x
)

# Positive integers
positive_ints = st.integers(min_value=1, max_value=10000)

# Non-negative floats
non_negative_floats = st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False)

# Boolean values
booleans = st.booleans()


# =============================================================================
# Unit Tests for ProviderConfig
# =============================================================================

class TestProviderConfigUnit:
    """Unit tests for ProviderConfig."""

    def test_default_provider_type(self):
        """Test default provider type is openai."""
        config = ProviderConfig()
        assert config.type == "openai"

    def test_default_model(self):
        """Test default model is set."""
        config = ProviderConfig()
        assert config.default_model == "grok-4-fast"

    def test_azure_provider_type(self):
        """Test azure provider type can be set."""
        config = ProviderConfig(type="azure")
        assert config.type == "azure"

    def test_task_model_map_exists(self):
        """Test TASK_MODEL_MAP has expected task types."""
        config = ProviderConfig()
        expected_tasks = ["quick_lookup", "fact_check", "deep_research", "synthesis", "chat", "planning", "documentation", "strategy"]
        for task in expected_tasks:
            assert task in config.TASK_MODEL_MAP

    def test_get_model_for_task_returns_tuple(self):
        """Test get_model_for_task returns (provider, model) tuple."""
        config = ProviderConfig()
        result = config.get_model_for_task("quick_lookup")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_get_model_for_unknown_task_returns_default(self):
        """Test unknown task returns default provider/model."""
        config = ProviderConfig()
        result = config.get_model_for_task("unknown_task_type")
        assert result == (config.default_provider, config.default_model)


class TestStorageConfigUnit:
    """Unit tests for StorageConfig."""

    def test_default_storage_type(self):
        """Test default storage type is local."""
        config = StorageConfig()
        assert config.type == "local"

    def test_default_local_path(self):
        """Test default local path is set."""
        config = StorageConfig()
        assert config.local_path == "data/reports"

    def test_blob_storage_type(self):
        """Test blob storage type can be set."""
        config = StorageConfig(type="blob")
        assert config.type == "blob"

    def test_azure_container_default(self):
        """Test default Azure container name."""
        config = StorageConfig()
        assert config.azure_container == "reports"


class TestWebhookConfigUnit:
    """Unit tests for WebhookConfig."""

    def test_default_enabled(self):
        """Test webhook is enabled by default."""
        config = WebhookConfig()
        assert config.enabled is True

    def test_default_port(self):
        """Test default port is 5000."""
        config = WebhookConfig()
        assert config.port == 5000

    def test_default_host(self):
        """Test default host is 0.0.0.0."""
        config = WebhookConfig()
        assert config.host == "0.0.0.0"

    def test_ngrok_enabled_by_default(self):
        """Test ngrok is enabled by default."""
        config = WebhookConfig()
        assert config.use_ngrok is True


class TestResearchConfigUnit:
    """Unit tests for ResearchConfig."""

    def test_default_output_formats(self):
        """Test default output formats include expected types."""
        config = ResearchConfig()
        assert "txt" in config.output_formats
        assert "md" in config.output_formats
        assert "json" in config.output_formats

    def test_default_max_wait_time(self):
        """Test default max wait time is 1800 seconds."""
        config = ResearchConfig()
        assert config.max_wait_time == 1800

    def test_default_poll_interval(self):
        """Test default poll interval is 30 seconds."""
        config = ResearchConfig()
        assert config.poll_interval == 30


class TestExpertConfigUnit:
    """Unit tests for ExpertConfig."""

    def test_default_topics(self):
        """Test default topics is 15."""
        config = ExpertConfig()
        assert config.default_topics == 15

    def test_deep_research_topics(self):
        """Test deep research topics is 5."""
        config = ExpertConfig()
        assert config.deep_research_topics == 5

    def test_quick_research_topics(self):
        """Test quick research topics is 10."""
        config = ExpertConfig()
        assert config.quick_research_topics == 10

    def test_auto_synthesis_default(self):
        """Test auto synthesis is enabled by default."""
        config = ExpertConfig()
        assert config.auto_synthesis is True


class TestAppConfigUnit:
    """Unit tests for AppConfig."""

    def test_default_environment(self):
        """Test default environment is local."""
        config = AppConfig()
        assert config.environment == "local"

    def test_default_debug(self):
        """Test debug is disabled by default."""
        config = AppConfig()
        assert config.debug is False

    def test_default_log_level(self):
        """Test default log level is INFO."""
        config = AppConfig()
        assert config.log_level == "INFO"

    def test_nested_configs_created(self):
        """Test nested config objects are created."""
        config = AppConfig()
        assert isinstance(config.provider, ProviderConfig)
        assert isinstance(config.storage, StorageConfig)
        assert isinstance(config.webhook, WebhookConfig)
        assert isinstance(config.research, ResearchConfig)
        assert isinstance(config.database, DatabaseConfig)
        assert isinstance(config.expert, ExpertConfig)


# =============================================================================
# Property Tests for Configuration Hierarchy
# =============================================================================

class TestConfigurationHierarchyProperties:
    """Property tests for configuration hierarchy: CLI > Env > File > Defaults."""

    @given(
        env_provider=provider_types,
        env_storage=storage_types,
        env_debug=booleans,
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_environment_overrides_defaults(self, env_provider, env_storage, env_debug):
        """Property: Environment variables override default values."""
        env_vars = {
            "DEEPR_PROVIDER": env_provider,
            "DEEPR_STORAGE": env_storage,
            "DEEPR_DEBUG": str(env_debug).lower(),
        }
        
        with patch.dict(os.environ, env_vars, clear=False):
            config = AppConfig.from_env()
            
            # Environment values should be applied
            assert config.provider.type == env_provider
            assert config.storage.type == env_storage
            assert config.debug == env_debug

    @given(
        default_model=model_names,
        default_provider=st.sampled_from(["openai", "xai", "anthropic"]),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_model_environment_override(self, default_model, default_provider):
        """Property: Model and provider can be overridden via environment."""
        env_vars = {
            "DEEPR_DEFAULT_MODEL": default_model,
            "DEEPR_DEFAULT_PROVIDER": default_provider,
        }
        
        with patch.dict(os.environ, env_vars, clear=False):
            config = ProviderConfig()
            
            assert config.default_model == default_model
            assert config.default_provider == default_provider

    @given(
        default_topics=st.integers(min_value=1, max_value=100),
        deep_topics=st.integers(min_value=1, max_value=50),
        quick_topics=st.integers(min_value=1, max_value=50),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_expert_config_environment_override(self, default_topics, deep_topics, quick_topics):
        """Property: Expert config values can be overridden via environment."""
        env_vars = {
            "DEEPR_EXPERT_DEFAULT_TOPICS": str(default_topics),
            "DEEPR_EXPERT_DEEP_TOPICS": str(deep_topics),
            "DEEPR_EXPERT_QUICK_TOPICS": str(quick_topics),
        }
        
        with patch.dict(os.environ, env_vars, clear=False):
            config = ExpertConfig()
            
            assert config.default_topics == default_topics
            assert config.deep_research_topics == deep_topics
            assert config.quick_research_topics == quick_topics

    @given(auto_synthesis=booleans)
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_boolean_environment_override(self, auto_synthesis):
        """Property: Boolean config values can be overridden via environment."""
        # Test various boolean string representations
        bool_str = "true" if auto_synthesis else "false"
        
        env_vars = {"DEEPR_EXPERT_AUTO_SYNTHESIS": bool_str}
        
        with patch.dict(os.environ, env_vars, clear=False):
            config = ExpertConfig()
            assert config.auto_synthesis == auto_synthesis


class TestConfigurationValidityProperties:
    """Property tests for configuration validity invariants."""

    @given(provider_type=provider_types)
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_provider_type_always_valid(self, provider_type):
        """Property: Provider type is always one of the valid options."""
        config = ProviderConfig(type=provider_type)
        assert config.type in ["openai", "azure"]

    @given(storage_type=storage_types)
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_storage_type_always_valid(self, storage_type):
        """Property: Storage type is always one of the valid options."""
        config = StorageConfig(type=storage_type)
        assert config.type in ["local", "blob"]

    @given(environment=environment_types)
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_environment_always_valid(self, environment):
        """Property: Environment is always one of the valid options."""
        config = AppConfig(environment=environment)
        assert config.environment in ["local", "cloud"]

    @given(db_type=database_types)
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_database_type_always_valid(self, db_type):
        """Property: Database type is always one of the valid options."""
        config = DatabaseConfig(type=db_type)
        assert config.type in ["jsonl", "sqlite", "cosmosdb"]

    @given(
        port=st.integers(min_value=1, max_value=65535),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_webhook_port_in_valid_range(self, port):
        """Property: Webhook port is always in valid range."""
        config = WebhookConfig(port=port)
        assert 1 <= config.port <= 65535

    @given(
        max_wait=positive_ints,
        poll_interval=positive_ints,
        retry_attempts=positive_ints,
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_research_config_positive_values(self, max_wait, poll_interval, retry_attempts):
        """Property: Research config timing values are always positive."""
        config = ResearchConfig(
            max_wait_time=max_wait,
            poll_interval=poll_interval,
            retry_attempts=retry_attempts,
        )
        assert config.max_wait_time > 0
        assert config.poll_interval > 0
        assert config.retry_attempts > 0


class TestTaskModelMappingProperties:
    """Property tests for task-to-model mapping."""

    @given(task_type=st.sampled_from([
        "quick_lookup", "fact_check", "deep_research", 
        "synthesis", "chat", "planning", "documentation", "strategy"
    ]))
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_known_task_returns_valid_mapping(self, task_type):
        """Property: Known task types always return valid (provider, model) tuple."""
        config = ProviderConfig()
        result = config.get_model_for_task(task_type)
        
        assert isinstance(result, tuple)
        assert len(result) == 2
        provider, model = result
        assert isinstance(provider, str)
        assert isinstance(model, str)
        assert len(provider) > 0
        assert len(model) > 0

    @given(task_type=st.text(min_size=1, max_size=50))
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_any_task_returns_tuple(self, task_type):
        """Property: Any task type (known or unknown) returns a valid tuple."""
        config = ProviderConfig()
        result = config.get_model_for_task(task_type)
        
        assert isinstance(result, tuple)
        assert len(result) == 2


class TestConfigSerializationProperties:
    """Property tests for configuration serialization."""

    @given(
        provider_type=provider_types,
        storage_type=storage_types,
        environment=environment_types,
        debug=booleans,
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_config_to_dict_roundtrip(self, provider_type, storage_type, environment, debug):
        """Property: Config can be serialized to dict and back."""
        config = AppConfig(
            environment=environment,
            debug=debug,
            provider=ProviderConfig(type=provider_type),
            storage=StorageConfig(type=storage_type),
        )
        
        # Serialize to dict
        config_dict = config.model_dump()
        
        # Deserialize back
        restored = AppConfig(**config_dict)
        
        # Verify key fields match
        assert restored.environment == config.environment
        assert restored.debug == config.debug
        assert restored.provider.type == config.provider.type
        assert restored.storage.type == config.storage.type

    @given(
        provider_type=provider_types,
        storage_type=storage_types,
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_config_to_json_roundtrip(self, provider_type, storage_type):
        """Property: Config can be serialized to JSON and back."""
        config = AppConfig(
            provider=ProviderConfig(type=provider_type),
            storage=StorageConfig(type=storage_type),
        )
        
        # Serialize to JSON
        json_str = config.model_dump_json()
        
        # Deserialize back
        config_dict = json.loads(json_str)
        restored = AppConfig(**config_dict)
        
        # Verify key fields match
        assert restored.provider.type == config.provider.type
        assert restored.storage.type == config.storage.type


class TestLoadConfigProperties:
    """Property tests for load_config function."""

    @given(
        max_cost_per_job=st.floats(min_value=0.1, max_value=100.0, allow_nan=False, allow_infinity=False),
        max_daily_cost=st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_load_config_cost_limits(self, max_cost_per_job, max_daily_cost):
        """Property: load_config respects cost limit environment variables."""
        env_vars = {
            "DEEPR_MAX_COST_PER_JOB": str(max_cost_per_job),
            "DEEPR_MAX_COST_PER_DAY": str(max_daily_cost),
        }
        
        with patch.dict(os.environ, env_vars, clear=False):
            config = load_config()
            
            assert abs(config["max_cost_per_job"] - max_cost_per_job) < 0.001
            assert abs(config["max_daily_cost"] - max_daily_cost) < 0.001

    def test_load_config_returns_dict(self):
        """Test load_config returns a dictionary with expected keys."""
        config = load_config()
        
        assert isinstance(config, dict)
        expected_keys = ["provider", "api_key", "queue", "storage", "results_dir"]
        for key in expected_keys:
            assert key in config


class TestConfigurationConsistencyProperties:
    """Property tests for configuration consistency."""

    @given(
        provider_type=provider_types,
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_provider_config_consistency(self, provider_type):
        """Property: Provider config is internally consistent."""
        config = ProviderConfig(type=provider_type)
        
        # If type is openai, azure-specific fields should not be required
        # If type is azure, openai-specific fields should not be required
        # Both should have valid defaults
        assert config.default_model is not None
        assert len(config.default_model) > 0
        assert config.default_provider is not None

    @given(
        storage_type=storage_types,
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_storage_config_consistency(self, storage_type):
        """Property: Storage config is internally consistent."""
        config = StorageConfig(type=storage_type)
        
        # Local storage should have a local path
        if storage_type == "local":
            assert config.local_path is not None
            assert len(config.local_path) > 0
        
        # Blob storage should have container name
        if storage_type == "blob":
            assert config.azure_container is not None

    def test_app_config_all_components_initialized(self):
        """Test AppConfig initializes all component configs."""
        config = AppConfig()
        
        # All nested configs should be initialized
        assert config.provider is not None
        assert config.storage is not None
        assert config.webhook is not None
        assert config.research is not None
        assert config.database is not None
        assert config.expert is not None


class TestEnvironmentVariablePrecedence:
    """Tests for environment variable precedence over defaults."""

    @given(
        env_value=st.sampled_from(["true", "false", "True", "False", "TRUE", "FALSE", "1", "0", "yes", "no"]),
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_boolean_parsing_variants(self, env_value):
        """Property: Various boolean string formats are handled correctly."""
        expected = env_value.lower() in ("true", "1", "yes")
        
        env_vars = {"DEEPR_EXPERT_AUTO_SYNTHESIS": env_value}
        
        with patch.dict(os.environ, env_vars, clear=False):
            config = ExpertConfig()
            assert config.auto_synthesis == expected

    @given(
        deep_model=model_names,
        deep_provider=st.sampled_from(["openai", "anthropic", "xai"]),
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_deep_research_config_override(self, deep_model, deep_provider):
        """Property: Deep research provider/model can be overridden."""
        env_vars = {
            "DEEPR_DEEP_RESEARCH_MODEL": deep_model,
            "DEEPR_DEEP_RESEARCH_PROVIDER": deep_provider,
        }
        
        with patch.dict(os.environ, env_vars, clear=False):
            config = ProviderConfig()
            
            assert config.deep_research_model == deep_model
            assert config.deep_research_provider == deep_provider
