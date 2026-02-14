"""Consolidated settings management for Deepr.

This module provides a single source of truth for all configuration through
the Settings class. It consolidates:
- Environment variables (DEEPR_*, provider API keys)
- Config files (~/.deepr/config.yaml, .deepr/config.yaml)
- CLI flags (passed at runtime)
- Defaults (in code)

Configuration hierarchy (lowest to highest priority):
1. Defaults (hardcoded)
2. Config file (YAML/JSON)
3. Environment variables
4. CLI flags

Usage:
    from deepr.core.settings import get_settings, Settings

    # Get singleton instance (recommended)
    settings = get_settings()

    # Or load with CLI overrides
    settings = Settings.load(cli_overrides={"provider": "azure"})

    # Access settings
    print(settings.default_provider)
    print(settings.get_api_key("openai"))
    print(settings.budget.daily_limit)

Requirements: 1.1 - Configuration Consolidation
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar, Literal, Optional

logger = logging.getLogger(__name__)

# =============================================================================
# Enums for type-safe configuration values
# =============================================================================


class ProviderType(str, Enum):
    """Supported LLM provider types."""

    OPENAI = "openai"
    AZURE = "azure"
    GEMINI = "gemini"
    GROK = "grok"
    XAI = "xai"
    ANTHROPIC = "anthropic"


class StorageType(str, Enum):
    """Supported storage backend types."""

    LOCAL = "local"
    BLOB = "blob"


class DatabaseType(str, Enum):
    """Supported database types for job metadata."""

    JSONL = "jsonl"
    SQLITE = "sqlite"
    COSMOSDB = "cosmosdb"


class ResearchMode(str, Enum):
    """Research execution modes."""

    READ_ONLY = "read_only"
    STANDARD = "standard"
    EXTENDED = "extended"
    UNRESTRICTED = "unrestricted"


class DomainVelocity(str, Enum):
    """Knowledge domain change velocity."""

    SLOW = "slow"  # 180 days threshold
    MEDIUM = "medium"  # 90 days threshold
    FAST = "fast"  # 30 days threshold


# =============================================================================
# Sub-configuration dataclasses
# =============================================================================


@dataclass
class ProviderSettings:
    """Settings for a single LLM provider."""

    name: str
    api_key: str = ""
    base_url: Optional[str] = None
    default_model: str = ""
    enabled: bool = True
    rate_limit: int = 60  # requests per minute
    timeout: int = 120  # seconds

    # Azure-specific
    azure_endpoint: Optional[str] = None
    azure_api_version: str = "2024-10-01-preview"
    azure_use_managed_identity: bool = False
    azure_deployment_map: dict[str, str] = field(default_factory=dict)

    def is_configured(self) -> bool:
        """Check if provider has required credentials."""
        if self.name == "azure":
            return bool(self.azure_endpoint and (self.api_key or self.azure_use_managed_identity))
        return bool(self.api_key)

    def to_dict(self, mask_keys: bool = True) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "api_key": "***" if mask_keys and self.api_key else self.api_key,
            "base_url": self.base_url,
            "default_model": self.default_model,
            "enabled": self.enabled,
            "rate_limit": self.rate_limit,
            "timeout": self.timeout,
            "is_configured": self.is_configured(),
        }


@dataclass
class StorageSettings:
    """Settings for storage backend."""

    type: StorageType = StorageType.LOCAL

    # Local storage
    local_path: str = "data/reports"

    # Azure Blob storage
    azure_connection_string: Optional[str] = None
    azure_account_url: Optional[str] = None
    azure_container: str = "reports"
    azure_use_managed_identity: bool = False

    def to_dict(self, mask_keys: bool = True) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.type.value,
            "local_path": self.local_path,
            "azure_container": self.azure_container,
            "azure_connection_string": "***"
            if mask_keys and self.azure_connection_string
            else self.azure_connection_string,
        }


@dataclass
class DatabaseSettings:
    """Settings for job metadata database."""

    type: DatabaseType = DatabaseType.JSONL

    # JSONL
    jsonl_path: str = "data/logs/job_log.jsonl"

    # SQLite
    sqlite_path: str = "data/logs/jobs.db"

    # CosmosDB
    cosmosdb_endpoint: Optional[str] = None
    cosmosdb_key: Optional[str] = None
    cosmosdb_database: str = "deepr"
    cosmosdb_container: str = "jobs"

    def to_dict(self, mask_keys: bool = True) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.type.value,
            "jsonl_path": self.jsonl_path,
            "sqlite_path": self.sqlite_path,
            "cosmosdb_endpoint": self.cosmosdb_endpoint,
            "cosmosdb_key": "***" if mask_keys and self.cosmosdb_key else self.cosmosdb_key,
        }


@dataclass
class BudgetSettings:
    """Budget and cost limit settings."""

    max_cost_per_job: float = 5.0
    daily_limit: float = 25.0
    monthly_limit: float = 200.0

    # Alert thresholds (percentage of limit)
    alert_threshold_50: float = 0.50
    alert_threshold_80: float = 0.80
    alert_threshold_95: float = 0.95

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "max_cost_per_job": self.max_cost_per_job,
            "daily_limit": self.daily_limit,
            "monthly_limit": self.monthly_limit,
            "alert_threshold_50": self.alert_threshold_50,
            "alert_threshold_80": self.alert_threshold_80,
            "alert_threshold_95": self.alert_threshold_95,
        }


@dataclass
class ResearchSettings:
    """Settings for research behavior."""

    # Output
    output_formats: list[str] = field(default_factory=lambda: ["txt", "md", "json", "docx"])
    generate_pdf: bool = False
    append_references: bool = False
    strip_inline_citations: bool = True

    # Job management
    max_wait_time: int = 1800  # seconds
    poll_interval: int = 30  # seconds
    retry_attempts: int = 5
    retry_delay: int = 30  # seconds

    # Batch processing
    batch_pause_every: int = 5
    batch_pause_duration: int = 180  # seconds

    # Quality settings
    entropy_threshold: float = 0.15
    min_information_gain: float = 0.10
    entropy_window_size: int = 3
    min_iterations_before_stop: int = 2

    # Token budgets
    token_budget_default: int = 50000
    token_budget_synthesis_reserve_pct: float = 0.20
    max_context_tokens: int = 8000

    # Default mode
    default_mode: ResearchMode = ResearchMode.STANDARD

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "output_formats": self.output_formats,
            "generate_pdf": self.generate_pdf,
            "max_wait_time": self.max_wait_time,
            "poll_interval": self.poll_interval,
            "entropy_threshold": self.entropy_threshold,
            "token_budget_default": self.token_budget_default,
            "default_mode": self.default_mode.value,
        }


@dataclass
class ExpertSettings:
    """Settings for expert system."""

    # Curriculum
    default_topics: int = 15
    deep_research_topics: int = 5
    quick_research_topics: int = 10

    # Costs
    deep_research_cost: float = 1.0  # per topic
    quick_research_cost: float = 0.002  # per topic

    # Synthesis
    auto_synthesis: bool = True
    synthesis_model: str = "gpt-5.2"

    # Freshness
    default_domain_velocity: DomainVelocity = DomainVelocity.MEDIUM
    staleness_threshold_days: int = 90

    # Budget
    monthly_learning_budget: float = 5.0
    max_context_tokens: int = 8000

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "default_topics": self.default_topics,
            "deep_research_topics": self.deep_research_topics,
            "quick_research_topics": self.quick_research_topics,
            "auto_synthesis": self.auto_synthesis,
            "default_domain_velocity": self.default_domain_velocity.value,
            "monthly_learning_budget": self.monthly_learning_budget,
        }


@dataclass
class WebhookSettings:
    """Settings for webhook server."""

    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 5000
    use_ngrok: bool = True
    ngrok_path: str = "ngrok"
    public_url: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "host": self.host,
            "port": self.port,
            "use_ngrok": self.use_ngrok,
            "public_url": self.public_url,
        }


@dataclass
class SecuritySettings:
    """Security-related settings."""

    # Instruction verification
    instruction_max_age: int = 300  # seconds

    # Task execution
    max_concurrent_tasks: int = 5
    task_default_timeout: int = 600  # seconds
    task_checkpoint_interval: int = 30  # seconds

    # Circuit breaker
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout: int = 60  # seconds

    # Provider health
    confidence_threshold: float = 0.7
    health_decay_factor: float = 0.95
    rolling_window_size: int = 20
    min_success_rate: float = 0.8
    max_stored_fallback_events: int = 100

    # Cost tracking
    cost_buffer_size: int = 10
    cost_flush_interval: int = 30  # seconds

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "instruction_max_age": self.instruction_max_age,
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "circuit_breaker_failure_threshold": self.circuit_breaker_failure_threshold,
            "confidence_threshold": self.confidence_threshold,
        }


# =============================================================================
# Task-to-model mapping
# =============================================================================

# Maps task types to (provider, model) tuples for optimal routing
TASK_MODEL_MAP: dict[str, tuple[str, str]] = {
    "quick_lookup": ("xai", "grok-4-fast"),
    "fact_check": ("xai", "grok-4-fast"),
    "deep_research": ("openai", "o3-deep-research"),
    "synthesis": ("openai", "gpt-5.2"),
    "chat": ("openai", "gpt-5.2"),
    "planning": ("openai", "gpt-5.2"),
    "documentation": ("openai", "gpt-5.2"),
    "strategy": ("openai", "gpt-5.2"),
}


# =============================================================================
# Main Settings class
# =============================================================================


@dataclass
class Settings:
    """Consolidated settings for Deepr.

    Single source of truth for all configuration. Loads from:
    1. Defaults (hardcoded here)
    2. Config file (~/.deepr/config.yaml or .deepr/config.yaml)
    3. Environment variables (DEEPR_*, API keys)
    4. CLI flags (highest priority)

    Attributes:
        environment: Deployment environment (local/cloud)
        debug: Enable debug mode
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        default_provider: Default LLM provider for operations
        default_model: Default model
        deep_research_provider: Provider for deep research (typically OpenAI)
        deep_research_model: Model for deep research
        data_dir: Base data directory
        providers: Per-provider configurations
        storage: Storage backend settings
        database: Job database settings
        budget: Budget and cost limits
        research: Research behavior settings
        expert: Expert system settings
        webhook: Webhook server settings
        security: Security settings
    """

    # Application settings
    environment: Literal["local", "cloud"] = "local"
    debug: bool = False
    log_level: str = "INFO"

    # Provider selection
    default_provider: str = "xai"
    default_model: str = "grok-4-fast"
    deep_research_provider: str = "openai"
    deep_research_model: str = "o3-deep-research"

    # Data directory
    data_dir: str = "data"

    # Sub-configurations
    providers: dict[str, ProviderSettings] = field(default_factory=dict)
    storage: StorageSettings = field(default_factory=StorageSettings)
    database: DatabaseSettings = field(default_factory=DatabaseSettings)
    budget: BudgetSettings = field(default_factory=BudgetSettings)
    research: ResearchSettings = field(default_factory=ResearchSettings)
    expert: ExpertSettings = field(default_factory=ExpertSettings)
    webhook: WebhookSettings = field(default_factory=WebhookSettings)
    security: SecuritySettings = field(default_factory=SecuritySettings)

    # Metadata (not persisted)
    _source: str = field(default="defaults", repr=False)
    _overrides: dict[str, str] = field(default_factory=dict, repr=False)
    _config_path: Optional[Path] = field(default=None, repr=False)

    # Singleton instance
    _instance: ClassVar[Optional[Settings]] = None

    # ==========================================================================
    # Loading methods
    # ==========================================================================

    @classmethod
    def load(
        cls,
        config_path: Optional[Path] = None,
        cli_overrides: Optional[dict[str, Any]] = None,
        reset_singleton: bool = False,
    ) -> Settings:
        """Load settings from all sources.

        Args:
            config_path: Explicit path to config file
            cli_overrides: CLI flag overrides (highest priority)
            reset_singleton: Force reload even if cached

        Returns:
            Settings instance
        """
        # Return cached instance if available
        if cls._instance is not None and not reset_singleton and not cli_overrides:
            return cls._instance

        settings = cls()

        # 1. Apply config file
        settings._apply_config_file(config_path)

        # 2. Apply environment variables
        settings._apply_environment()

        # 3. Apply CLI overrides
        if cli_overrides:
            settings._apply_cli_overrides(cli_overrides)

        # Cache as singleton
        cls._instance = settings
        return settings

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance (useful for testing)."""
        cls._instance = None

    def _apply_config_file(self, config_path: Optional[Path] = None) -> None:
        """Apply settings from config file."""
        if config_path is None:
            config_path = self._find_config_file()

        if config_path is None or not config_path.exists():
            return

        try:
            if config_path.suffix in (".yaml", ".yml"):
                try:
                    import yaml

                    with open(config_path, encoding="utf-8") as f:
                        data = yaml.safe_load(f) or {}
                except ImportError:
                    return
            else:
                with open(config_path, encoding="utf-8") as f:
                    data = json.load(f)

            self._apply_dict(data, source=f"file:{config_path}")
            self._config_path = config_path
            self._source = str(config_path)

        except Exception as e:
            logger.warning("Failed to load config from %s: %s", config_path, e)

    def _apply_environment(self) -> None:
        """Apply environment variable overrides."""
        # Core settings
        self._apply_env("DEEPR_ENVIRONMENT", "environment")
        self._apply_env("DEEPR_DEBUG", "debug", type_=bool)
        self._apply_env("DEEPR_LOG_LEVEL", "log_level")

        # Provider selection
        self._apply_env("DEEPR_DEFAULT_PROVIDER", "default_provider")
        self._apply_env("DEEPR_DEFAULT_MODEL", "default_model")
        self._apply_env("DEEPR_DEEP_RESEARCH_PROVIDER", "deep_research_provider")
        self._apply_env("DEEPR_DEEP_RESEARCH_MODEL", "deep_research_model")

        # Data directory
        self._apply_env("DEEPR_DATA_DIR", "data_dir")

        # Provider API keys
        self._load_provider_from_env("openai", "OPENAI_API_KEY", "OPENAI_BASE_URL", "gpt-5.2")
        self._load_provider_from_env("anthropic", "ANTHROPIC_API_KEY", None, "claude-opus-4-5-20251101")
        self._load_provider_from_env("gemini", "GEMINI_API_KEY", None, "gemini-2.0-flash")
        self._load_provider_from_env("grok", "XAI_API_KEY", None, "grok-4-fast")
        self._load_provider_from_env("xai", "XAI_API_KEY", None, "grok-4-fast")

        # Azure (special handling)
        azure_key = os.getenv("AZURE_OPENAI_KEY")
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        if azure_key or azure_endpoint:
            if "azure" not in self.providers:
                self.providers["azure"] = ProviderSettings(name="azure")
            self.providers["azure"].api_key = azure_key or ""
            self.providers["azure"].azure_endpoint = azure_endpoint
            self.providers["azure"].azure_api_version = os.getenv("AZURE_API_VERSION", "2024-10-01-preview")
            self.providers["azure"].azure_use_managed_identity = _parse_bool(
                os.getenv("AZURE_USE_MANAGED_IDENTITY", "false")
            )
            self._overrides["providers.azure"] = "env"

        # Storage settings
        storage_type = os.getenv("DEEPR_STORAGE")
        if storage_type:
            self.storage.type = StorageType(storage_type)
            self._overrides["storage.type"] = "env"

        self._apply_env("DEEPR_REPORTS_PATH", "storage.local_path")

        azure_conn = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        if azure_conn:
            self.storage.azure_connection_string = azure_conn
            self._overrides["storage.azure_connection_string"] = "env"

        # Database settings
        db_type = os.getenv("DEEPR_DATABASE_TYPE")
        if db_type:
            self.database.type = DatabaseType(db_type)
            self._overrides["database.type"] = "env"

        self._apply_env("DEEPR_JSONL_PATH", "database.jsonl_path")
        self._apply_env("DEEPR_SQLITE_PATH", "database.sqlite_path")

        # Budget settings
        self._apply_env("DEEPR_MAX_COST_PER_JOB", "budget.max_cost_per_job", type_=float)
        self._apply_env("DEEPR_MAX_COST_PER_DAY", "budget.daily_limit", type_=float)
        self._apply_env("DEEPR_DAILY_LIMIT", "budget.daily_limit", type_=float)
        self._apply_env("DEEPR_MAX_COST_PER_MONTH", "budget.monthly_limit", type_=float)
        self._apply_env("DEEPR_MONTHLY_LIMIT", "budget.monthly_limit", type_=float)

        # Research settings
        self._apply_env("DEEPR_GENERATE_PDF", "research.generate_pdf", type_=bool)
        self._apply_env("DEEPR_APPEND_REFERENCES", "research.append_references", type_=bool)
        self._apply_env("DEEPR_STRIP_INLINE_CITATIONS", "research.strip_inline_citations", type_=bool)
        self._apply_env("DEEPR_MAX_WAIT_TIME", "research.max_wait_time", type_=int)
        self._apply_env("DEEPR_POLL_INTERVAL", "research.poll_interval", type_=int)
        self._apply_env("DEEPR_RETRY_ATTEMPTS", "research.retry_attempts", type_=int)
        self._apply_env("DEEPR_RETRY_DELAY", "research.retry_delay", type_=int)
        self._apply_env("DEEPR_BATCH_PAUSE_EVERY", "research.batch_pause_every", type_=int)
        self._apply_env("DEEPR_BATCH_PAUSE_DURATION", "research.batch_pause_duration", type_=int)
        self._apply_env("DEEPR_ENTROPY_THRESHOLD", "research.entropy_threshold", type_=float)
        self._apply_env("DEEPR_MIN_INFORMATION_GAIN", "research.min_information_gain", type_=float)
        self._apply_env("DEEPR_TOKEN_BUDGET_DEFAULT", "research.token_budget_default", type_=int)
        self._apply_env("DEEPR_MAX_CONTEXT_TOKENS", "research.max_context_tokens", type_=int)

        research_mode = os.getenv("DEEPR_DEFAULT_RESEARCH_MODE")
        if research_mode:
            self.research.default_mode = ResearchMode(research_mode)
            self._overrides["research.default_mode"] = "env"

        # Expert settings
        self._apply_env("DEEPR_EXPERT_DEFAULT_TOPICS", "expert.default_topics", type_=int)
        self._apply_env("DEEPR_EXPERT_DEEP_TOPICS", "expert.deep_research_topics", type_=int)
        self._apply_env("DEEPR_EXPERT_QUICK_TOPICS", "expert.quick_research_topics", type_=int)
        self._apply_env("DEEPR_EXPERT_AUTO_SYNTHESIS", "expert.auto_synthesis", type_=bool)

        # Webhook settings
        self._apply_env("DEEPR_WEBHOOK_ENABLED", "webhook.enabled", type_=bool)
        self._apply_env("DEEPR_WEBHOOK_HOST", "webhook.host")
        self._apply_env("DEEPR_WEBHOOK_PORT", "webhook.port", type_=int)
        self._apply_env("DEEPR_USE_NGROK", "webhook.use_ngrok", type_=bool)
        self._apply_env("NGROK_PATH", "webhook.ngrok_path")
        self._apply_env("DEEPR_WEBHOOK_URL", "webhook.public_url")

        # Security settings
        self._apply_env("DEEPR_INSTRUCTION_MAX_AGE", "security.instruction_max_age", type_=int)
        self._apply_env("DEEPR_MAX_CONCURRENT_TASKS", "security.max_concurrent_tasks", type_=int)
        self._apply_env("DEEPR_TASK_DEFAULT_TIMEOUT", "security.task_default_timeout", type_=int)
        self._apply_env("DEEPR_TASK_CHECKPOINT_INTERVAL", "security.task_checkpoint_interval", type_=int)
        self._apply_env(
            "DEEPR_CIRCUIT_BREAKER_FAILURE_THRESHOLD", "security.circuit_breaker_failure_threshold", type_=int
        )
        self._apply_env(
            "DEEPR_CIRCUIT_BREAKER_RECOVERY_TIMEOUT", "security.circuit_breaker_recovery_timeout", type_=int
        )
        self._apply_env("DEEPR_CONFIDENCE_THRESHOLD", "security.confidence_threshold", type_=float)
        self._apply_env("DEEPR_HEALTH_DECAY_FACTOR", "security.health_decay_factor", type_=float)
        self._apply_env("DEEPR_ROLLING_WINDOW_SIZE", "security.rolling_window_size", type_=int)
        self._apply_env("DEEPR_MIN_SUCCESS_RATE", "security.min_success_rate", type_=float)
        self._apply_env("DEEPR_MAX_STORED_FALLBACK_EVENTS", "security.max_stored_fallback_events", type_=int)
        self._apply_env("DEEPR_COST_BUFFER_SIZE", "security.cost_buffer_size", type_=int)
        self._apply_env("DEEPR_COST_FLUSH_INTERVAL", "security.cost_flush_interval", type_=int)

    def _apply_cli_overrides(self, overrides: dict[str, Any]) -> None:
        """Apply CLI flag overrides."""
        for key, value in overrides.items():
            if value is not None:
                self._set_nested(key, value)
                self._overrides[key] = "cli"

    def _apply_dict(self, data: dict[str, Any], source: str = "dict") -> None:
        """Apply dictionary configuration."""
        # Core settings
        for key in [
            "environment",
            "debug",
            "log_level",
            "default_provider",
            "default_model",
            "deep_research_provider",
            "deep_research_model",
            "data_dir",
        ]:
            if key in data:
                setattr(self, key, data[key])
                self._overrides[key] = source

        # Providers
        if "providers" in data:
            for name, pdata in data["providers"].items():
                self.providers[name] = ProviderSettings(
                    name=name,
                    api_key=pdata.get("api_key", ""),
                    base_url=pdata.get("base_url"),
                    default_model=pdata.get("default_model", ""),
                    enabled=pdata.get("enabled", True),
                    rate_limit=pdata.get("rate_limit", 60),
                    timeout=pdata.get("timeout", 120),
                )
                self._overrides[f"providers.{name}"] = source

        # Sub-configurations
        if "storage" in data:
            self._apply_storage_dict(data["storage"], source)
        if "database" in data:
            self._apply_database_dict(data["database"], source)
        if "budget" in data:
            self._apply_budget_dict(data["budget"], source)
        if "research" in data:
            self._apply_research_dict(data["research"], source)
        if "expert" in data:
            self._apply_expert_dict(data["expert"], source)
        if "webhook" in data:
            self._apply_webhook_dict(data["webhook"], source)
        if "security" in data:
            self._apply_security_dict(data["security"], source)

    def _apply_storage_dict(self, data: dict[str, Any], source: str) -> None:
        """Apply storage configuration from dict."""
        if "type" in data:
            self.storage.type = StorageType(data["type"])
        for key in [
            "local_path",
            "azure_connection_string",
            "azure_account_url",
            "azure_container",
            "azure_use_managed_identity",
        ]:
            if key in data:
                setattr(self.storage, key, data[key])
        self._overrides["storage"] = source

    def _apply_database_dict(self, data: dict[str, Any], source: str) -> None:
        """Apply database configuration from dict."""
        if "type" in data:
            self.database.type = DatabaseType(data["type"])
        for key in [
            "jsonl_path",
            "sqlite_path",
            "cosmosdb_endpoint",
            "cosmosdb_key",
            "cosmosdb_database",
            "cosmosdb_container",
        ]:
            if key in data:
                setattr(self.database, key, data[key])
        self._overrides["database"] = source

    def _apply_budget_dict(self, data: dict[str, Any], source: str) -> None:
        """Apply budget configuration from dict."""
        for key in [
            "max_cost_per_job",
            "daily_limit",
            "monthly_limit",
            "alert_threshold_50",
            "alert_threshold_80",
            "alert_threshold_95",
        ]:
            if key in data:
                setattr(self.budget, key, data[key])
        self._overrides["budget"] = source

    def _apply_research_dict(self, data: dict[str, Any], source: str) -> None:
        """Apply research configuration from dict."""
        for key in [
            "output_formats",
            "generate_pdf",
            "append_references",
            "strip_inline_citations",
            "max_wait_time",
            "poll_interval",
            "retry_attempts",
            "retry_delay",
            "batch_pause_every",
            "batch_pause_duration",
            "entropy_threshold",
            "min_information_gain",
            "entropy_window_size",
            "min_iterations_before_stop",
            "token_budget_default",
            "token_budget_synthesis_reserve_pct",
            "max_context_tokens",
        ]:
            if key in data:
                setattr(self.research, key, data[key])
        if "default_mode" in data:
            self.research.default_mode = ResearchMode(data["default_mode"])
        self._overrides["research"] = source

    def _apply_expert_dict(self, data: dict[str, Any], source: str) -> None:
        """Apply expert configuration from dict."""
        for key in [
            "default_topics",
            "deep_research_topics",
            "quick_research_topics",
            "deep_research_cost",
            "quick_research_cost",
            "auto_synthesis",
            "synthesis_model",
            "staleness_threshold_days",
            "monthly_learning_budget",
            "max_context_tokens",
        ]:
            if key in data:
                setattr(self.expert, key, data[key])
        if "default_domain_velocity" in data:
            self.expert.default_domain_velocity = DomainVelocity(data["default_domain_velocity"])
        self._overrides["expert"] = source

    def _apply_webhook_dict(self, data: dict[str, Any], source: str) -> None:
        """Apply webhook configuration from dict."""
        for key in ["enabled", "host", "port", "use_ngrok", "ngrok_path", "public_url"]:
            if key in data:
                setattr(self.webhook, key, data[key])
        self._overrides["webhook"] = source

    def _apply_security_dict(self, data: dict[str, Any], source: str) -> None:
        """Apply security configuration from dict."""
        for key in [
            "instruction_max_age",
            "max_concurrent_tasks",
            "task_default_timeout",
            "task_checkpoint_interval",
            "circuit_breaker_failure_threshold",
            "circuit_breaker_recovery_timeout",
            "confidence_threshold",
            "health_decay_factor",
            "rolling_window_size",
            "min_success_rate",
            "max_stored_fallback_events",
            "cost_buffer_size",
            "cost_flush_interval",
        ]:
            if key in data:
                setattr(self.security, key, data[key])
        self._overrides["security"] = source

    def _apply_env(self, env_var: str, setting_path: str, type_: type = str) -> None:
        """Apply single environment variable."""
        value = os.getenv(env_var)
        if value is not None:
            if type_ is bool:
                value = _parse_bool(value)
            elif type_ is int:
                value = int(value)
            elif type_ is float:
                value = float(value)
            self._set_nested(setting_path, value)
            self._overrides[setting_path] = "env"

    def _load_provider_from_env(self, name: str, key_var: str, url_var: Optional[str], default_model: str) -> None:
        """Load provider configuration from environment."""
        api_key = os.getenv(key_var)
        if api_key:
            if name not in self.providers:
                self.providers[name] = ProviderSettings(name=name, default_model=default_model)
            self.providers[name].api_key = api_key
            if url_var:
                base_url = os.getenv(url_var)
                if base_url:
                    self.providers[name].base_url = base_url
            self._overrides[f"providers.{name}"] = "env"

    def _set_nested(self, path: str, value: Any) -> None:
        """Set a nested configuration value using dot notation."""
        parts = path.split(".")
        if len(parts) == 1:
            if hasattr(self, path):
                setattr(self, path, value)
        elif len(parts) == 2:
            container = getattr(self, parts[0], None)
            if container is not None and hasattr(container, parts[1]):
                setattr(container, parts[1], value)

    def _find_config_file(self) -> Optional[Path]:
        """Find configuration file in standard locations."""
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

    # ==========================================================================
    # Accessor methods
    # ==========================================================================

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by dot-separated key.

        Args:
            key: Dot-separated key path (e.g., "budget.daily_limit")
            default: Default value if not found

        Returns:
            Configuration value
        """
        parts = key.split(".")
        current: Any = self

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

    def get_provider(self, name: Optional[str] = None) -> Optional[ProviderSettings]:
        """Get provider configuration.

        Args:
            name: Provider name. If None, returns default provider.

        Returns:
            ProviderSettings or None
        """
        provider_name = name or self.default_provider
        return self.providers.get(provider_name)

    def get_api_key(self, provider: Optional[str] = None) -> str:
        """Get API key for a provider.

        Args:
            provider: Provider name. If None, returns default provider's key.

        Returns:
            API key or empty string
        """
        provider_settings = self.get_provider(provider)
        return provider_settings.api_key if provider_settings else ""

    def get_model_for_task(self, task_type: str) -> tuple[str, str]:
        """Get optimal (provider, model) for a task type.

        Args:
            task_type: One of quick_lookup, fact_check, deep_research,
                      synthesis, chat, planning, documentation, strategy

        Returns:
            Tuple of (provider, model) for the task
        """
        if task_type in TASK_MODEL_MAP:
            return TASK_MODEL_MAP[task_type]
        return (self.default_provider, self.default_model)

    # ==========================================================================
    # Validation
    # ==========================================================================

    def validate(self) -> list[str]:
        """Validate configuration.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check default provider has API key
        if self.default_provider:
            provider = self.get_provider(self.default_provider)
            if provider is None:
                errors.append(f"Default provider '{self.default_provider}' not configured")
            elif not provider.is_configured():
                errors.append(f"No API key for default provider '{self.default_provider}'")

        # Check data directory exists or can be created
        data_path = Path(self.data_dir)
        if not data_path.exists():
            try:
                data_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                errors.append(f"Cannot create data directory '{self.data_dir}': {e}")

        # Check budget limits are positive
        if self.budget.daily_limit <= 0:
            errors.append("Daily budget limit must be positive")
        if self.budget.monthly_limit <= 0:
            errors.append("Monthly budget limit must be positive")

        return errors

    # ==========================================================================
    # Serialization
    # ==========================================================================

    def to_dict(self, mask_keys: bool = True) -> dict[str, Any]:
        """Convert to dictionary.

        Args:
            mask_keys: Whether to mask API keys

        Returns:
            Dictionary representation
        """
        return {
            "environment": self.environment,
            "debug": self.debug,
            "log_level": self.log_level,
            "default_provider": self.default_provider,
            "default_model": self.default_model,
            "deep_research_provider": self.deep_research_provider,
            "deep_research_model": self.deep_research_model,
            "data_dir": self.data_dir,
            "providers": {name: p.to_dict(mask_keys=mask_keys) for name, p in self.providers.items()},
            "storage": self.storage.to_dict(mask_keys=mask_keys),
            "database": self.database.to_dict(mask_keys=mask_keys),
            "budget": self.budget.to_dict(),
            "research": self.research.to_dict(),
            "expert": self.expert.to_dict(),
            "webhook": self.webhook.to_dict(),
            "security": self.security.to_dict(),
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
            "=" * 50,
            f"Source: {self._source}",
            "",
            "Core Settings:",
            f"  Environment: {self.environment}",
            f"  Debug: {self.debug}",
            f"  Log Level: {self.log_level}",
            f"  Data Dir: {self.data_dir}",
            "",
            "Provider Settings:",
            f"  Default Provider: {self.default_provider}",
            f"  Default Model: {self.default_model}",
            f"  Deep Research Provider: {self.deep_research_provider}",
            f"  Deep Research Model: {self.deep_research_model}",
            "",
            "Configured Providers:",
        ]

        for name, config in self.providers.items():
            key_display = "***" if mask_keys and config.api_key else (config.api_key or "(not set)")
            status = "enabled" if config.enabled and config.is_configured() else "disabled"
            lines.append(f"  {name}:")
            lines.append(f"    API Key: {key_display}")
            lines.append(f"    Model: {config.default_model or '(default)'}")
            lines.append(f"    Status: {status}")

        lines.extend(
            [
                "",
                "Storage:",
                f"  Type: {self.storage.type.value}",
                f"  Path: {self.storage.local_path}",
                "",
                "Budget Limits:",
                f"  Per Job: ${self.budget.max_cost_per_job:.2f}",
                f"  Daily: ${self.budget.daily_limit:.2f}",
                f"  Monthly: ${self.budget.monthly_limit:.2f}",
            ]
        )

        if self._overrides:
            lines.extend(["", "Overrides:"])
            for key, source in sorted(self._overrides.items()):
                lines.append(f"  {key}: from {source}")

        return "\n".join(lines)


# =============================================================================
# Helper functions
# =============================================================================


def _parse_bool(value: str) -> bool:
    """Parse boolean from string."""
    return value.lower() in ("true", "1", "yes", "on")


def get_settings(cli_overrides: Optional[dict[str, Any]] = None, reset: bool = False) -> Settings:
    """Get the global Settings instance.

    This is the recommended way to access settings. It returns a cached
    singleton instance that is loaded once and reused.

    Args:
        cli_overrides: CLI flag overrides (forces reload if provided)
        reset: Force reload of settings

    Returns:
        Settings instance

    Example:
        settings = get_settings()
        print(settings.default_provider)
        print(settings.get_api_key("openai"))
    """
    return Settings.load(cli_overrides=cli_overrides, reset_singleton=reset)


# =============================================================================
# Legacy compatibility
# =============================================================================


def load_config() -> dict[str, Any]:
    """Legacy function for loading configuration as dictionary.

    Deprecated: Use get_settings() instead.

    Returns:
        Dictionary with configuration values matching legacy format
    """
    settings = get_settings()

    api_key = settings.get_api_key("openai")
    if not api_key:
        api_key = settings.get_api_key(settings.default_provider)

    return {
        "provider": settings.default_provider,
        "api_key": api_key,
        "azure_endpoint": settings.providers.get("azure", ProviderSettings("azure")).azure_endpoint,
        "queue": "local",
        "queue_db_path": "queue/research_queue.db",
        "storage": settings.storage.type.value,
        "results_dir": settings.storage.local_path,
        "max_cost_per_job": settings.budget.max_cost_per_job,
        "max_daily_cost": settings.budget.daily_limit,
        "max_monthly_cost": settings.budget.monthly_limit,
    }
