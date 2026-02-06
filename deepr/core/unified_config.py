"""Unified configuration management for Deepr.

Consolidates configuration from multiple sources with clear hierarchy:
1. Defaults (lowest priority)
2. Config file (~/.deepr/config.yaml or .deepr/config.yaml)
3. Environment variables
4. CLI flags (highest priority)

Usage:
    from deepr.config.unified import UnifiedConfig

    config = UnifiedConfig.load()
    print(config.default_provider)
    print(config.get("api_keys.openai"))
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ProviderConfig:
    """Configuration for a provider.

    Attributes:
        name: Provider name
        api_key: API key (masked in output)
        default_model: Default model for provider
        enabled: Whether provider is enabled
        rate_limit: Rate limit (requests per minute)
        timeout: Request timeout in seconds
    """

    name: str
    api_key: str = ""
    default_model: str = ""
    enabled: bool = True
    rate_limit: int = 60
    timeout: int = 120

    def to_dict(self, mask_keys: bool = True) -> Dict[str, Any]:
        return {
            "name": self.name,
            "api_key": "***" if mask_keys and self.api_key else self.api_key,
            "default_model": self.default_model,
            "enabled": self.enabled,
            "rate_limit": self.rate_limit,
            "timeout": self.timeout,
        }


@dataclass
class UnifiedConfig:
    """Unified configuration for Deepr.

    Attributes:
        default_provider: Default LLM provider
        default_model: Default model
        data_dir: Data directory path
        log_level: Logging level
        providers: Provider configurations
        expert_defaults: Default expert settings
        research_defaults: Default research settings
        budget_limits: Budget limits
    """

    # Core settings
    default_provider: str = "openai"
    default_model: str = "gpt-4o"
    data_dir: str = "data"
    log_level: str = "INFO"

    # Provider configurations
    providers: Dict[str, ProviderConfig] = field(default_factory=dict)

    # Expert defaults
    expert_defaults: Dict[str, Any] = field(
        default_factory=lambda: {
            "monthly_learning_budget": 5.0,
            "staleness_threshold_days": 90,
            "max_context_tokens": 8000,
        }
    )

    # Research defaults
    research_defaults: Dict[str, Any] = field(
        default_factory=lambda: {"max_rounds": 5, "default_budget": 1.0, "parallel_searches": 3}
    )

    # Budget limits
    budget_limits: Dict[str, float] = field(
        default_factory=lambda: {
            "daily_limit": 10.0,
            "monthly_limit": 100.0,
            "alert_threshold_50": 0.5,
            "alert_threshold_80": 0.8,
            "alert_threshold_95": 0.95,
        }
    )

    # Internal tracking
    _source: str = "defaults"
    _overrides: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(
        cls, config_path: Optional[Path] = None, cli_overrides: Optional[Dict[str, Any]] = None
    ) -> "UnifiedConfig":
        """Load configuration from all sources.

        Args:
            config_path: Optional explicit config file path
            cli_overrides: CLI flag overrides

        Returns:
            UnifiedConfig instance
        """
        config = cls()

        # 1. Load from config file
        config._apply_file(config_path)

        # 2. Apply environment variables
        config._apply_env()

        # 3. Apply CLI overrides
        if cli_overrides:
            config._apply_cli(cli_overrides)

        return config

    @classmethod
    def from_app_config(cls, app_config: Any) -> "UnifiedConfig":
        """Create UnifiedConfig from AppConfig.

        This provides a bridge from the legacy Pydantic-based AppConfig
        to the new UnifiedConfig system.

        Args:
            app_config: AppConfig instance

        Returns:
            UnifiedConfig instance
        """
        config = cls()
        config._source = "AppConfig"

        # Map provider settings
        if hasattr(app_config, "provider"):
            provider = app_config.provider
            config.default_provider = getattr(provider, "default_provider", "openai")
            config.default_model = getattr(provider, "default_model", "gpt-4o")

            # Map provider API keys
            if getattr(provider, "openai_api_key", None):
                config.providers["openai"] = ProviderConfig(
                    name="openai",
                    api_key=provider.openai_api_key,
                    default_model=getattr(provider, "default_model", "gpt-4o"),
                    enabled=True,
                )

            if getattr(provider, "azure_api_key", None):
                config.providers["azure"] = ProviderConfig(
                    name="azure",
                    api_key=provider.azure_api_key,
                    default_model=getattr(provider, "default_model", "gpt-4o"),
                    enabled=True,
                )

        # Map storage settings
        if hasattr(app_config, "storage"):
            storage = app_config.storage
            config.data_dir = getattr(storage, "local_path", "data")

        # Map log level
        config.log_level = getattr(app_config, "log_level", "INFO")

        # Map expert defaults
        if hasattr(app_config, "expert"):
            expert = app_config.expert
            config.expert_defaults = {
                "monthly_learning_budget": 5.0,
                "staleness_threshold_days": 90,
                "max_context_tokens": 8000,
                "default_topics": getattr(expert, "default_topics", 15),
                "deep_research_topics": getattr(expert, "deep_research_topics", 5),
                "quick_research_topics": getattr(expert, "quick_research_topics", 10),
                "auto_synthesis": getattr(expert, "auto_synthesis", True),
            }

        return config

    def _apply_file(self, config_path: Optional[Path] = None):
        """Apply configuration from file.

        Args:
            config_path: Optional explicit path
        """
        # Find config file
        if config_path is None:
            config_path = self._find_config_file()

        if config_path is None or not config_path.exists():
            return

        try:
            if config_path.suffix in (".yaml", ".yml"):
                try:
                    import yaml

                    with open(config_path, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f) or {}
                except ImportError:
                    return
            else:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

            self._apply_dict(data, source="file")
            self._source = str(config_path)

        except Exception:
            pass  # Silently ignore config file errors

    def _apply_env(self):
        """Apply environment variable overrides."""
        env_mappings = {
            "DEEPR_PROVIDER": "default_provider",
            "DEEPR_MODEL": "default_model",
            "DEEPR_DATA_DIR": "data_dir",
            "DEEPR_LOG_LEVEL": "log_level",
            "DEEPR_DAILY_LIMIT": "budget_limits.daily_limit",
            "DEEPR_MONTHLY_LIMIT": "budget_limits.monthly_limit",
        }

        for env_var, config_key in env_mappings.items():
            value = os.environ.get(env_var)
            if value:
                self._set_nested(config_key, value)
                self._overrides[config_key] = "env"

        # Provider API keys
        provider_keys = {
            "OPENAI_API_KEY": "openai",
            "ANTHROPIC_API_KEY": "anthropic",
            "GOOGLE_API_KEY": "gemini",
            "AZURE_OPENAI_API_KEY": "azure",
            "XAI_API_KEY": "grok",
        }

        for env_var, provider in provider_keys.items():
            value = os.environ.get(env_var)
            if value:
                if provider not in self.providers:
                    self.providers[provider] = ProviderConfig(name=provider)
                self.providers[provider].api_key = value
                self._overrides[f"providers.{provider}.api_key"] = "env"

    def _apply_cli(self, overrides: Dict[str, Any]):
        """Apply CLI flag overrides.

        Args:
            overrides: Dictionary of CLI overrides
        """
        for key, value in overrides.items():
            if value is not None:
                self._set_nested(key, value)
                self._overrides[key] = "cli"

    def _apply_dict(self, data: Dict[str, Any], source: str = "dict"):
        """Apply dictionary configuration.

        Args:
            data: Configuration dictionary
            source: Source identifier
        """
        simple_fields = ["default_provider", "default_model", "data_dir", "log_level"]

        for field_name in simple_fields:
            if field_name in data:
                setattr(self, field_name, data[field_name])
                self._overrides[field_name] = source

        # Nested configurations
        if "providers" in data:
            for name, pdata in data["providers"].items():
                self.providers[name] = ProviderConfig(
                    name=name,
                    api_key=pdata.get("api_key", ""),
                    default_model=pdata.get("default_model", ""),
                    enabled=pdata.get("enabled", True),
                    rate_limit=pdata.get("rate_limit", 60),
                    timeout=pdata.get("timeout", 120),
                )
                self._overrides[f"providers.{name}"] = source

        if "expert_defaults" in data:
            self.expert_defaults.update(data["expert_defaults"])
            self._overrides["expert_defaults"] = source

        if "research_defaults" in data:
            self.research_defaults.update(data["research_defaults"])
            self._overrides["research_defaults"] = source

        if "budget_limits" in data:
            self.budget_limits.update(data["budget_limits"])
            self._overrides["budget_limits"] = source

    def _set_nested(self, key: str, value: Any):
        """Set a nested configuration value.

        Args:
            key: Dot-separated key path
            value: Value to set
        """
        parts = key.split(".")

        if len(parts) == 1:
            if hasattr(self, key):
                # Convert type if needed
                current = getattr(self, key)
                if isinstance(current, float):
                    value = float(value)
                elif isinstance(current, int):
                    value = int(value)
                setattr(self, key, value)
        elif len(parts) == 2:
            container_name, field_name = parts
            container = getattr(self, container_name, None)
            if isinstance(container, dict):
                # Convert type if needed
                if field_name in container:
                    current = container[field_name]
                    if isinstance(current, float):
                        value = float(value)
                    elif isinstance(current, int):
                        value = int(value)
                container[field_name] = value

    def _find_config_file(self) -> Optional[Path]:
        """Find configuration file.

        Returns:
            Path to config file or None
        """
        # Check locations in order
        locations = [
            Path(".deepr/config.yaml"),
            Path(".deepr/config.yml"),
            Path(".deepr/config.json"),
            Path.home() / ".deepr" / "config.yaml",
            Path.home() / ".deepr" / "config.yml",
            Path.home() / ".deepr" / "config.json",
        ]

        for path in locations:
            if path.exists():
                return path

        return None

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key.

        Args:
            key: Dot-separated key path
            default: Default value if not found

        Returns:
            Configuration value
        """
        parts = key.split(".")

        if len(parts) == 1:
            return getattr(self, key, default)

        # Navigate nested structure
        current = self
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                return default

            if current is None:
                return default

        return current

    def get_provider_config(self, provider: str) -> Optional[ProviderConfig]:
        """Get configuration for a provider.

        Args:
            provider: Provider name

        Returns:
            ProviderConfig or None
        """
        return self.providers.get(provider)

    def get_api_key(self, provider: str) -> str:
        """Get API key for a provider.

        Args:
            provider: Provider name

        Returns:
            API key or empty string
        """
        config = self.providers.get(provider)
        return config.api_key if config else ""

    def validate(self) -> List[str]:
        """Validate configuration.

        Returns:
            List of validation errors
        """
        errors = []

        # Check default provider has API key
        if self.default_provider:
            if self.default_provider not in self.providers:
                errors.append(f"Default provider '{self.default_provider}' not configured")
            elif not self.providers[self.default_provider].api_key:
                errors.append(f"No API key for default provider '{self.default_provider}'")

        # Check data directory
        data_path = Path(self.data_dir)
        if not data_path.exists():
            errors.append(f"Data directory '{self.data_dir}' does not exist")

        # Check budget limits
        if self.budget_limits.get("daily_limit", 0) <= 0:
            errors.append("Daily budget limit must be positive")

        return errors

    def to_dict(self, mask_keys: bool = True) -> Dict[str, Any]:
        """Convert to dictionary.

        Args:
            mask_keys: Whether to mask API keys

        Returns:
            Dictionary representation
        """
        return {
            "default_provider": self.default_provider,
            "default_model": self.default_model,
            "data_dir": self.data_dir,
            "log_level": self.log_level,
            "providers": {name: p.to_dict(mask_keys=mask_keys) for name, p in self.providers.items()},
            "expert_defaults": self.expert_defaults,
            "research_defaults": self.research_defaults,
            "budget_limits": self.budget_limits,
            "_source": self._source,
            "_overrides": self._overrides,
        }

    def show(self, mask_keys: bool = True) -> str:
        """Generate human-readable configuration display.

        Args:
            mask_keys: Whether to mask API keys

        Returns:
            Formatted configuration string
        """
        lines = [
            "Deepr Configuration",
            "=" * 40,
            f"Source: {self._source}",
            "",
            "Core Settings:",
            f"  Provider: {self.default_provider}",
            f"  Model: {self.default_model}",
            f"  Data Dir: {self.data_dir}",
            f"  Log Level: {self.log_level}",
            "",
            "Providers:",
        ]

        for name, config in self.providers.items():
            key_display = "***" if mask_keys and config.api_key else (config.api_key or "(not set)")
            lines.append(f"  {name}:")
            lines.append(f"    API Key: {key_display}")
            lines.append(f"    Model: {config.default_model or '(default)'}")
            lines.append(f"    Enabled: {config.enabled}")

        lines.extend(
            [
                "",
                "Budget Limits:",
                f"  Daily: ${self.budget_limits.get('daily_limit', 0):.2f}",
                f"  Monthly: ${self.budget_limits.get('monthly_limit', 0):.2f}",
            ]
        )

        if self._overrides:
            lines.extend(["", "Overrides:"])
            for key, source in self._overrides.items():
                lines.append(f"  {key}: from {source}")

        return "\n".join(lines)
