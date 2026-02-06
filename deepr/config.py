"""Configuration management for Deepr."""

import os
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Load .env file
load_dotenv()


class ProviderConfig(BaseModel):
    """Configuration for AI provider (OpenAI or Azure)."""

    model_config = ConfigDict(validate_default=True)

    type: Literal["openai", "azure"] = Field(default="openai", description="Provider type: openai or azure")

    # OpenAI Configuration
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key")
    openai_base_url: Optional[str] = Field(default=None, description="Custom OpenAI base URL")
    openai_organization: Optional[str] = Field(default=None, description="OpenAI organization ID")

    # Azure Configuration
    azure_api_key: Optional[str] = Field(default=None, description="Azure OpenAI API key")
    azure_endpoint: Optional[str] = Field(default=None, description="Azure OpenAI endpoint URL")
    azure_api_version: str = Field(default="2024-10-01-preview", description="Azure OpenAI API version")
    azure_use_managed_identity: bool = Field(default=False, description="Use Azure Managed Identity for authentication")

    # Model/Deployment Mappings
    default_model: str = Field(default="grok-4-fast", description="Default model to use")
    model_mappings: Dict[str, str] = Field(
        default_factory=dict, description="Model key to deployment name mappings (Azure)"
    )

    # Dual Provider Configuration
    default_provider: str = Field(default="xai", description="Default provider for general operations")
    deep_research_provider: str = Field(default="openai", description="Provider for deep research operations")
    deep_research_model: str = Field(default="o3-deep-research", description="Model for deep research")

    # Task-specific model mappings
    # Maps task types to (provider, model) tuples
    TASK_MODEL_MAP: Dict[str, tuple] = {
        "quick_lookup": ("xai", "grok-4-fast"),  # Fast, cheap fact checks
        "fact_check": ("xai", "grok-4-fast"),  # Fact verification
        "deep_research": ("openai", "o3-deep-research"),  # Deep research (BEST model)
        "synthesis": ("openai", "gpt-5"),  # Knowledge synthesis
        "chat": ("openai", "gpt-5"),  # Expert chat
        "planning": ("openai", "gpt-5"),  # Research planning
        "documentation": ("openai", "gpt-5"),  # Doc generation
        "strategy": ("openai", "gpt-5.2"),  # Strategic analysis
    }

    def get_model_for_task(self, task_type: str) -> tuple:
        """Get optimal (provider, model) for a task type.

        Args:
            task_type: One of quick_lookup, fact_check, deep_research,
                      synthesis, chat, planning, documentation, strategy

        Returns:
            Tuple of (provider, model) for the task
        """
        if task_type in self.TASK_MODEL_MAP:
            return self.TASK_MODEL_MAP[task_type]
        # Default fallback
        return (self.default_provider, self.default_model)

    @field_validator("default_provider", mode="before")
    @classmethod
    def validate_default_provider(cls, v: Any) -> str:
        """Load default provider from environment."""
        return os.getenv("DEEPR_DEFAULT_PROVIDER", v) if v else os.getenv("DEEPR_DEFAULT_PROVIDER", "xai")

    @field_validator("default_model", mode="before")
    @classmethod
    def validate_default_model(cls, v: Any) -> str:
        """Load default model from environment."""
        return os.getenv("DEEPR_DEFAULT_MODEL", v) if v else os.getenv("DEEPR_DEFAULT_MODEL", "grok-4-fast")

    @field_validator("deep_research_provider", mode="before")
    @classmethod
    def validate_deep_research_provider(cls, v: Any) -> str:
        """Load deep research provider from environment."""
        return (
            os.getenv("DEEPR_DEEP_RESEARCH_PROVIDER", v) if v else os.getenv("DEEPR_DEEP_RESEARCH_PROVIDER", "openai")
        )

    @field_validator("deep_research_model", mode="before")
    @classmethod
    def validate_deep_research_model(cls, v: Any) -> str:
        """Load deep research model from environment."""
        return (
            os.getenv("DEEPR_DEEP_RESEARCH_MODEL", v)
            if v
            else os.getenv("DEEPR_DEEP_RESEARCH_MODEL", "o3-deep-research")
        )

    @model_validator(mode="after")
    def validate_api_keys(self) -> "ProviderConfig":
        """Validate API keys based on provider type."""
        if self.type == "openai" and not self.openai_api_key:
            self.openai_api_key = os.getenv("OPENAI_API_KEY")
        if self.type == "azure":
            if not self.azure_use_managed_identity and not self.azure_api_key:
                self.azure_api_key = os.getenv("AZURE_OPENAI_KEY")
            if not self.azure_endpoint:
                self.azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        return self


class StorageConfig(BaseModel):
    """Configuration for storage backend (local or Azure Blob)."""

    model_config = ConfigDict(validate_default=True)

    type: Literal["local", "blob"] = Field(default="local", description="Storage type: local or blob")

    # Local Storage Configuration
    local_path: str = Field(default="data/reports", description="Local storage directory path")

    # Azure Blob Storage Configuration
    azure_connection_string: Optional[str] = Field(default=None, description="Azure Storage connection string")
    azure_account_url: Optional[str] = Field(
        default=None, description="Azure Storage account URL (for managed identity)"
    )
    azure_container: str = Field(default="reports", description="Azure Blob container name")
    azure_use_managed_identity: bool = Field(default=False, description="Use Azure Managed Identity for storage")

    @model_validator(mode="after")
    def validate_azure_storage(self) -> "StorageConfig":
        """Validate Azure storage configuration."""
        if self.type == "blob":
            if not self.azure_use_managed_identity and not self.azure_connection_string:
                self.azure_connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
            if self.azure_use_managed_identity and not self.azure_account_url:
                self.azure_account_url = os.getenv("AZURE_STORAGE_ACCOUNT_URL")
        return self


class WebhookConfig(BaseModel):
    """Configuration for webhook server."""

    enabled: bool = Field(default=True, description="Enable webhook server")
    port: int = Field(default=5000, description="Webhook server port")
    host: str = Field(default="0.0.0.0", description="Webhook server host")

    # Ngrok Configuration (for local development)
    use_ngrok: bool = Field(default=True, description="Use ngrok tunnel for local development")
    ngrok_path: str = Field(default="ngrok", description="Path to ngrok executable")

    # Cloud Configuration
    public_url: Optional[str] = Field(default=None, description="Public webhook URL (for cloud deployment)")


class ResearchConfig(BaseModel):
    """Configuration for research behavior."""

    # System Message
    system_message_file: str = Field(default="system_message.json", description="Path to system message configuration")

    # Output Configuration
    output_formats: list = Field(
        default=["txt", "md", "json", "docx"],
        description="Output formats to generate (txt, md, json, docx, pdf)",
    )
    generate_pdf: bool = Field(default=False, description="Generate PDF output")
    append_references: bool = Field(default=False, description="Append extracted references to reports")
    strip_inline_citations: bool = Field(default=True, description="Remove inline citations from output")

    # Job Management
    max_wait_time: int = Field(default=1800, description="Maximum wait time for jobs (seconds)")
    poll_interval: int = Field(default=30, description="Job polling interval (seconds)")
    retry_attempts: int = Field(default=5, description="Number of retry attempts for downloads")
    retry_delay: int = Field(default=30, description="Delay between retries (seconds)")

    # Batch Processing
    batch_pause_every: int = Field(default=5, description="Pause after N batch jobs")
    batch_pause_duration: int = Field(default=180, description="Batch pause duration (seconds)")


class ExpertConfig(BaseModel):
    """Configuration for expert system."""

    model_config = ConfigDict(validate_default=True)

    # Curriculum Generation
    default_topics: int = Field(default=15, description="Default number of learning topics")
    deep_research_topics: int = Field(default=5, description="Number of deep research (campaign) topics")
    quick_research_topics: int = Field(default=10, description="Number of quick research (focus) topics")

    # Cost Estimates (averages based on actual model costs)
    deep_research_cost: float = Field(
        default=1.0, description="Average cost per deep research topic (CAMPAIGN mode: o4-mini-deep-research)"
    )
    quick_research_cost: float = Field(
        default=0.002, description="Average cost per quick research topic (FOCUS mode: grok-4-fast)"
    )

    # Synthesis
    auto_synthesis: bool = Field(default=True, description="Automatically synthesize knowledge after learning")
    synthesis_model: str = Field(default="gpt-5", description="Model for knowledge synthesis")

    # Domain Velocity Defaults
    default_domain_velocity: str = Field(default="medium", description="Default domain velocity (slow/medium/fast)")

    @field_validator("default_topics", mode="before")
    @classmethod
    def validate_default_topics(cls, v: Any) -> int:
        """Load default topics from environment."""
        env_val = os.getenv("DEEPR_EXPERT_DEFAULT_TOPICS")
        return int(env_val) if env_val else (int(v) if v else 15)

    @field_validator("deep_research_topics", mode="before")
    @classmethod
    def validate_deep_topics(cls, v: Any) -> int:
        """Load deep research topics from environment."""
        env_val = os.getenv("DEEPR_EXPERT_DEEP_TOPICS")
        return int(env_val) if env_val else (int(v) if v else 5)

    @field_validator("quick_research_topics", mode="before")
    @classmethod
    def validate_quick_topics(cls, v: Any) -> int:
        """Load quick research topics from environment."""
        env_val = os.getenv("DEEPR_EXPERT_QUICK_TOPICS")
        return int(env_val) if env_val else (int(v) if v else 10)

    @field_validator("auto_synthesis", mode="before")
    @classmethod
    def validate_auto_synthesis(cls, v: Any) -> bool:
        """Load auto synthesis from environment."""
        env_val = os.getenv("DEEPR_EXPERT_AUTO_SYNTHESIS")
        if env_val:
            return env_val.lower() in ("true", "1", "yes")
        return bool(v) if v is not None else True


class DatabaseConfig(BaseModel):
    """Configuration for job metadata database."""

    type: Literal["jsonl", "sqlite", "cosmosdb"] = Field(default="jsonl", description="Database type")

    # JSONL Configuration
    jsonl_path: str = Field(default="data/logs/job_log.jsonl", description="Path to JSONL log file")

    # SQLite Configuration
    sqlite_path: str = Field(default="data/logs/jobs.db", description="Path to SQLite database")

    # Cosmos DB Configuration
    cosmosdb_endpoint: Optional[str] = Field(default=None, description="Cosmos DB endpoint")
    cosmosdb_key: Optional[str] = Field(default=None, description="Cosmos DB key")
    cosmosdb_database: str = Field(default="deepr", description="Cosmos DB database name")
    cosmosdb_container: str = Field(default="jobs", description="Cosmos DB container name")


class AppConfig(BaseModel):
    """Main application configuration."""

    # Environment
    environment: Literal["local", "cloud"] = Field(default="local", description="Deployment environment")

    # Component Configurations
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    webhook: WebhookConfig = Field(default_factory=WebhookConfig)
    research: ResearchConfig = Field(default_factory=ResearchConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    expert: ExpertConfig = Field(default_factory=ExpertConfig)

    # Application Settings
    debug: bool = Field(default=False, description="Enable debug mode")
    log_level: str = Field(default="INFO", description="Logging level")

    @classmethod
    def from_env(cls) -> "AppConfig":
        """
        Load configuration from environment variables.

        Environment variable mapping:
        - DEEPR_PROVIDER: openai or azure
        - DEEPR_STORAGE: local or blob
        - DEEPR_ENVIRONMENT: local or cloud
        - DEEPR_DEBUG: true or false
        """
        # Determine provider type
        provider_type = os.getenv("DEEPR_PROVIDER", "openai")

        provider = ProviderConfig(
            type=provider_type,
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_base_url=os.getenv("OPENAI_BASE_URL"),
            openai_organization=os.getenv("OPENAI_ORGANIZATION"),
            azure_api_key=os.getenv("AZURE_OPENAI_KEY"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            azure_api_version=os.getenv("AZURE_API_VERSION", "2024-10-01-preview"),
            azure_use_managed_identity=os.getenv("AZURE_USE_MANAGED_IDENTITY", "false").lower() == "true",
            default_model=os.getenv("DEEPR_DEFAULT_MODEL", "o3-deep-research"),
            model_mappings={
                "o3-deep-research": os.getenv("AZURE_DEPLOYMENT_O3", "o3-deep-research"),
                "o4-mini-deep-research": os.getenv("AZURE_DEPLOYMENT_O4_MINI", "o4-mini-deep-research"),
            },
        )

        # Determine storage type
        storage_type = os.getenv("DEEPR_STORAGE", "local")

        storage = StorageConfig(
            type=storage_type,
            local_path=os.getenv("DEEPR_REPORTS_PATH", "data/reports"),
            azure_connection_string=os.getenv("AZURE_STORAGE_CONNECTION_STRING"),
            azure_account_url=os.getenv("AZURE_STORAGE_ACCOUNT_URL"),
            azure_container=os.getenv("AZURE_STORAGE_CONTAINER", "reports"),
            azure_use_managed_identity=os.getenv("AZURE_STORAGE_USE_MANAGED_IDENTITY", "false").lower() == "true",
        )

        # Determine environment
        environment = os.getenv("DEEPR_ENVIRONMENT", "local")

        webhook = WebhookConfig(
            enabled=os.getenv("DEEPR_WEBHOOK_ENABLED", "true").lower() == "true",
            port=int(os.getenv("DEEPR_WEBHOOK_PORT", "5000")),
            use_ngrok=environment == "local",
            ngrok_path=os.getenv("NGROK_PATH", "ngrok"),
            public_url=os.getenv("DEEPR_WEBHOOK_URL"),
        )

        research = ResearchConfig(
            generate_pdf=os.getenv("DEEPR_GENERATE_PDF", "false").lower() == "true",
            append_references=os.getenv("DEEPR_APPEND_REFERENCES", "false").lower() == "true",
        )

        database = DatabaseConfig(
            type=os.getenv("DEEPR_DATABASE_TYPE", "jsonl"),
            jsonl_path=os.getenv("DEEPR_JSONL_PATH", "data/logs/job_log.jsonl"),
        )

        return cls(
            environment=environment,
            provider=provider,
            storage=storage,
            webhook=webhook,
            research=research,
            database=database,
            debug=os.getenv("DEEPR_DEBUG", "false").lower() == "true",
            log_level=os.getenv("DEEPR_LOG_LEVEL", "INFO"),
        )

    def to_env_file(self, path: str = ".env.example"):
        """
        Generate example .env file with current configuration.

        Args:
            path: Path to write .env file
        """
        lines = [
            "# Deepr Configuration",
            "",
            "# Environment",
            f"DEEPR_ENVIRONMENT={self.environment}",
            f"DEEPR_DEBUG={str(self.debug).lower()}",
            f"DEEPR_LOG_LEVEL={self.log_level}",
            "",
            "# Provider Configuration",
            f"DEEPR_PROVIDER={self.provider.type}",
            "",
        ]

        if self.provider.type == "openai":
            lines.extend(
                [
                    "# OpenAI Configuration",
                    f"OPENAI_API_KEY={self.provider.openai_api_key or 'your-openai-api-key'}",
                    "# OPENAI_BASE_URL=https://api.openai.com/v1",
                    "# OPENAI_ORGANIZATION=your-org-id",
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    "# Azure OpenAI Configuration",
                    f"AZURE_OPENAI_KEY={self.provider.azure_api_key or 'your-azure-api-key'}",
                    f"AZURE_OPENAI_ENDPOINT={self.provider.azure_endpoint or 'https://your-resource.openai.azure.com/'}",
                    f"AZURE_API_VERSION={self.provider.azure_api_version}",
                    f"AZURE_USE_MANAGED_IDENTITY={str(self.provider.azure_use_managed_identity).lower()}",
                    "AZURE_DEPLOYMENT_O3=your-o3-deployment",
                    "AZURE_DEPLOYMENT_O4_MINI=your-o4-mini-deployment",
                    "",
                ]
            )

        lines.extend(
            [
                "# Storage Configuration",
                f"DEEPR_STORAGE={self.storage.type}",
                "",
            ]
        )

        if self.storage.type == "local":
            lines.extend([f"DEEPR_REPORTS_PATH={self.storage.local_path}", ""])
        else:
            lines.extend(
                [
                    "# Azure Blob Storage Configuration",
                    f"AZURE_STORAGE_CONNECTION_STRING={self.storage.azure_connection_string or 'your-connection-string'}",
                    f"AZURE_STORAGE_CONTAINER={self.storage.azure_container}",
                    f"AZURE_STORAGE_USE_MANAGED_IDENTITY={str(self.storage.azure_use_managed_identity).lower()}",
                    "",
                ]
            )

        Path(path).write_text("\n".join(lines))

    model_config = ConfigDict(
        env_prefix="DEEPR_",
        case_sensitive=False,
    )


def load_config() -> Dict:
    """
    Load configuration as a simple dictionary.

    Returns:
        Dictionary with configuration values
    """
    config = AppConfig.from_env()

    return {
        "provider": config.provider.type,
        "api_key": config.provider.openai_api_key
        if config.provider.type == "openai"
        else config.provider.azure_api_key,
        "azure_endpoint": config.provider.azure_endpoint,
        "queue": "local",  # Default to local queue
        "queue_db_path": "queue/research_queue.db",
        "storage": config.storage.type,
        "results_dir": config.storage.local_path,
        "max_cost_per_job": float(os.getenv("DEEPR_MAX_COST_PER_JOB", "5.0")),
        "max_daily_cost": float(os.getenv("DEEPR_MAX_COST_PER_DAY", "25.0")),
        "max_monthly_cost": float(os.getenv("DEEPR_MAX_COST_PER_MONTH", "200.0")),
    }
