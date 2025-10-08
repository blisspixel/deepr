"""Configuration management for Deepr."""

import os
from typing import Optional, Literal, Dict
from pydantic import BaseModel, Field, validator
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()


class ProviderConfig(BaseModel):
    """Configuration for AI provider (OpenAI or Azure)."""

    type: Literal["openai", "azure"] = Field(
        default="openai", description="Provider type: openai or azure"
    )

    # OpenAI Configuration
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key")
    openai_base_url: Optional[str] = Field(default=None, description="Custom OpenAI base URL")
    openai_organization: Optional[str] = Field(
        default=None, description="OpenAI organization ID"
    )

    # Azure Configuration
    azure_api_key: Optional[str] = Field(default=None, description="Azure OpenAI API key")
    azure_endpoint: Optional[str] = Field(default=None, description="Azure OpenAI endpoint URL")
    azure_api_version: str = Field(
        default="2024-10-01-preview", description="Azure OpenAI API version"
    )
    azure_use_managed_identity: bool = Field(
        default=False, description="Use Azure Managed Identity for authentication"
    )

    # Model/Deployment Mappings
    default_model: str = Field(default="o3-deep-research", description="Default model to use")
    model_mappings: Dict[str, str] = Field(
        default_factory=dict, description="Model key to deployment name mappings (Azure)"
    )

    @validator("openai_api_key", always=True)
    def validate_openai_key(cls, v, values):
        """Validate OpenAI API key is present when using OpenAI provider."""
        if values.get("type") == "openai" and not v:
            return os.getenv("OPENAI_API_KEY")
        return v

    @validator("azure_api_key", always=True)
    def validate_azure_key(cls, v, values):
        """Validate Azure API key when not using managed identity."""
        if values.get("type") == "azure" and not values.get("azure_use_managed_identity"):
            if not v:
                return os.getenv("AZURE_OPENAI_KEY")
        return v

    @validator("azure_endpoint", always=True)
    def validate_azure_endpoint(cls, v, values):
        """Validate Azure endpoint is present when using Azure provider."""
        if values.get("type") == "azure" and not v:
            return os.getenv("AZURE_OPENAI_ENDPOINT")
        return v


class StorageConfig(BaseModel):
    """Configuration for storage backend (local or Azure Blob)."""

    type: Literal["local", "blob"] = Field(
        default="local", description="Storage type: local or blob"
    )

    # Local Storage Configuration
    local_path: str = Field(default="data/reports", description="Local storage directory path")

    # Azure Blob Storage Configuration
    azure_connection_string: Optional[str] = Field(
        default=None, description="Azure Storage connection string"
    )
    azure_account_url: Optional[str] = Field(
        default=None, description="Azure Storage account URL (for managed identity)"
    )
    azure_container: str = Field(default="reports", description="Azure Blob container name")
    azure_use_managed_identity: bool = Field(
        default=False, description="Use Azure Managed Identity for storage"
    )

    @validator("azure_connection_string", always=True)
    def validate_blob_connection(cls, v, values):
        """Validate Azure Storage connection string when using blob storage."""
        if values.get("type") == "blob" and not values.get("azure_use_managed_identity"):
            if not v:
                return os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        return v

    @validator("azure_account_url", always=True)
    def validate_blob_account_url(cls, v, values):
        """Validate Azure Storage account URL for managed identity."""
        if (
            values.get("type") == "blob"
            and values.get("azure_use_managed_identity")
            and not v
        ):
            return os.getenv("AZURE_STORAGE_ACCOUNT_URL")
        return v


class WebhookConfig(BaseModel):
    """Configuration for webhook server."""

    enabled: bool = Field(default=True, description="Enable webhook server")
    port: int = Field(default=5000, description="Webhook server port")
    host: str = Field(default="0.0.0.0", description="Webhook server host")

    # Ngrok Configuration (for local development)
    use_ngrok: bool = Field(
        default=True, description="Use ngrok tunnel for local development"
    )
    ngrok_path: str = Field(default="ngrok", description="Path to ngrok executable")

    # Cloud Configuration
    public_url: Optional[str] = Field(
        default=None, description="Public webhook URL (for cloud deployment)"
    )


class ResearchConfig(BaseModel):
    """Configuration for research behavior."""

    # System Message
    system_message_file: str = Field(
        default="system_message.json", description="Path to system message configuration"
    )

    # Output Configuration
    output_formats: list = Field(
        default=["txt", "md", "json", "docx"],
        description="Output formats to generate (txt, md, json, docx, pdf)",
    )
    generate_pdf: bool = Field(default=False, description="Generate PDF output")
    append_references: bool = Field(
        default=False, description="Append extracted references to reports"
    )
    strip_inline_citations: bool = Field(
        default=True, description="Remove inline citations from output"
    )

    # Job Management
    max_wait_time: int = Field(default=1800, description="Maximum wait time for jobs (seconds)")
    poll_interval: int = Field(default=30, description="Job polling interval (seconds)")
    retry_attempts: int = Field(default=5, description="Number of retry attempts for downloads")
    retry_delay: int = Field(default=30, description="Delay between retries (seconds)")

    # Batch Processing
    batch_pause_every: int = Field(default=5, description="Pause after N batch jobs")
    batch_pause_duration: int = Field(default=180, description="Batch pause duration (seconds)")


class DatabaseConfig(BaseModel):
    """Configuration for job metadata database."""

    type: Literal["jsonl", "sqlite", "cosmosdb"] = Field(
        default="jsonl", description="Database type"
    )

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
    environment: Literal["local", "cloud"] = Field(
        default="local", description="Deployment environment"
    )

    # Component Configurations
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    webhook: WebhookConfig = Field(default_factory=WebhookConfig)
    research: ResearchConfig = Field(default_factory=ResearchConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)

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
            azure_use_managed_identity=os.getenv("AZURE_USE_MANAGED_IDENTITY", "false").lower()
            == "true",
            default_model=os.getenv("DEEPR_DEFAULT_MODEL", "o3-deep-research"),
            model_mappings={
                "o3-deep-research": os.getenv("AZURE_DEPLOYMENT_O3", "o3-deep-research"),
                "o4-mini-deep-research": os.getenv(
                    "AZURE_DEPLOYMENT_O4_MINI", "o4-mini-deep-research"
                ),
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
            azure_use_managed_identity=os.getenv("AZURE_STORAGE_USE_MANAGED_IDENTITY", "false").lower()
            == "true",
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

    class Config:
        """Pydantic configuration."""

        env_prefix = "DEEPR_"
        case_sensitive = False


def load_config() -> Dict:
    """
    Load configuration as a simple dictionary.

    Returns:
        Dictionary with configuration values
    """
    config = AppConfig.from_env()

    return {
        "provider": config.provider.type,
        "api_key": config.provider.openai_api_key if config.provider.type == "openai" else config.provider.azure_api_key,
        "azure_endpoint": config.provider.azure_endpoint,
        "queue": "local",  # Default to local queue
        "queue_db_path": "queue/research_queue.db",
        "storage": config.storage.type,
        "results_dir": config.storage.local_path,
        "max_cost_per_job": float(os.getenv("DEEPR_MAX_COST_PER_JOB", "10.0")),
        "max_daily_cost": float(os.getenv("DEEPR_MAX_COST_PER_DAY", "100.0")),
        "max_monthly_cost": float(os.getenv("DEEPR_MAX_COST_PER_MONTH", "1000.0")),
    }
