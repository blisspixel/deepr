"""Tests for application configuration (deepr/config.py)."""

from deepr.config import (
    AppConfig,
    DatabaseConfig,
    ExpertConfig,
    ProviderConfig,
    ResearchConfig,
    StorageConfig,
    WebhookConfig,
    load_config,
)


class TestProviderConfig:
    """Test ProviderConfig Pydantic model."""

    def test_defaults(self):
        """Default values are correct."""
        pc = ProviderConfig()
        assert pc.type == "openai"
        assert pc.azure_api_version == "2024-10-01-preview"
        assert pc.azure_use_managed_identity is False
        assert pc.model_mappings == {}

    def test_openai_api_key_from_env(self, monkeypatch):
        """openai_api_key pulled from OPENAI_API_KEY env."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env-test")
        pc = ProviderConfig(type="openai")
        assert pc.openai_api_key == "sk-env-test"

    def test_azure_api_key_from_env(self, monkeypatch):
        """azure_api_key pulled from AZURE_OPENAI_KEY env."""
        monkeypatch.setenv("AZURE_OPENAI_KEY", "az-key-123")
        pc = ProviderConfig(type="azure")
        assert pc.azure_api_key == "az-key-123"

    def test_azure_endpoint_from_env(self, monkeypatch):
        """azure_endpoint pulled from AZURE_OPENAI_ENDPOINT env."""
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://my.azure.com/")
        pc = ProviderConfig(type="azure")
        assert pc.azure_endpoint == "https://my.azure.com/"

    def test_default_provider_from_env(self, monkeypatch):
        """DEEPR_DEFAULT_PROVIDER overrides default."""
        monkeypatch.setenv("DEEPR_DEFAULT_PROVIDER", "azure")
        pc = ProviderConfig()
        assert pc.default_provider == "azure"

    def test_default_model_from_env(self, monkeypatch):
        """DEEPR_DEFAULT_MODEL overrides default."""
        monkeypatch.setenv("DEEPR_DEFAULT_MODEL", "custom-model")
        pc = ProviderConfig()
        assert pc.default_model == "custom-model"

    def test_deep_research_provider_from_env(self, monkeypatch):
        """DEEPR_DEEP_RESEARCH_PROVIDER overrides default."""
        monkeypatch.setenv("DEEPR_DEEP_RESEARCH_PROVIDER", "gemini")
        pc = ProviderConfig()
        assert pc.deep_research_provider == "gemini"

    def test_deep_research_model_from_env(self, monkeypatch):
        """DEEPR_DEEP_RESEARCH_MODEL overrides default."""
        monkeypatch.setenv("DEEPR_DEEP_RESEARCH_MODEL", "gemini-2.5-flash")
        pc = ProviderConfig()
        assert pc.deep_research_model == "gemini-2.5-flash"

    def test_get_model_for_task_known(self):
        """Known task types return expected (provider, model) tuples."""
        pc = ProviderConfig()
        provider, model = pc.get_model_for_task("deep_research")
        assert provider == "openai"
        assert model == "o3-deep-research"  # BEST model for deep research

    def test_get_model_for_task_unknown(self):
        """Unknown task falls back to (default_provider, default_model)."""
        pc = ProviderConfig()
        provider, model = pc.get_model_for_task("unknown_task_xyz")
        assert provider == pc.default_provider
        assert model == pc.default_model

    def test_task_model_map_completeness(self):
        """All expected task types present in TASK_MODEL_MAP."""
        pc = ProviderConfig()
        expected = {
            "quick_lookup",
            "fact_check",
            "deep_research",
            "synthesis",
            "chat",
            "planning",
            "documentation",
            "strategy",
        }
        assert expected == set(pc.TASK_MODEL_MAP.keys())


class TestStorageConfig:
    """Test StorageConfig Pydantic model."""

    def test_defaults(self):
        """Default values are correct."""
        sc = StorageConfig()
        assert sc.type == "local"
        assert sc.local_path == "data/reports"
        assert sc.azure_container == "reports"

    def test_blob_connection_string_from_env(self, monkeypatch):
        """Azure connection string from environment."""
        monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "conn-str-123")
        sc = StorageConfig(type="blob")
        assert sc.azure_connection_string == "conn-str-123"

    def test_blob_managed_identity_account_url(self, monkeypatch):
        """Managed identity loads account URL from env."""
        monkeypatch.setenv("AZURE_STORAGE_ACCOUNT_URL", "https://acct.blob.core.windows.net")
        sc = StorageConfig(type="blob", azure_use_managed_identity=True)
        assert sc.azure_account_url == "https://acct.blob.core.windows.net"

    def test_local_type_ignores_azure(self):
        """Local type does not validate Azure fields."""
        sc = StorageConfig(type="local")
        assert sc.azure_connection_string is None


class TestWebhookConfig:
    """Test WebhookConfig Pydantic model."""

    def test_defaults(self):
        """Default values are correct."""
        wc = WebhookConfig()
        assert wc.enabled is True
        assert wc.port == 5000
        assert wc.use_ngrok is True

    def test_custom_values(self):
        """Custom values accepted."""
        wc = WebhookConfig(port=8080, use_ngrok=False, public_url="https://example.com/hook")
        assert wc.port == 8080
        assert wc.use_ngrok is False
        assert wc.public_url == "https://example.com/hook"


class TestResearchConfig:
    """Test ResearchConfig Pydantic model."""

    def test_defaults(self):
        """Default values are correct."""
        rc = ResearchConfig()
        assert rc.max_wait_time == 1800
        assert rc.poll_interval == 30
        assert rc.batch_pause_every == 5
        assert rc.generate_pdf is False

    def test_output_formats_default(self):
        """Default output formats include txt, md, json, docx."""
        rc = ResearchConfig()
        assert set(rc.output_formats) == {"txt", "md", "json", "docx"}


class TestExpertConfig:
    """Test ExpertConfig Pydantic model."""

    def test_defaults(self):
        """Default values are correct."""
        ec = ExpertConfig()
        assert ec.default_topics == 15
        assert ec.deep_research_topics == 5
        assert ec.quick_research_topics == 10
        assert ec.auto_synthesis is True
        assert ec.synthesis_model == "gpt-5.2"

    def test_default_topics_from_env(self, monkeypatch):
        """DEEPR_EXPERT_DEFAULT_TOPICS overrides default."""
        monkeypatch.setenv("DEEPR_EXPERT_DEFAULT_TOPICS", "25")
        ec = ExpertConfig()
        assert ec.default_topics == 25

    def test_deep_topics_from_env(self, monkeypatch):
        """DEEPR_EXPERT_DEEP_TOPICS overrides default."""
        monkeypatch.setenv("DEEPR_EXPERT_DEEP_TOPICS", "8")
        ec = ExpertConfig()
        assert ec.deep_research_topics == 8

    def test_quick_topics_from_env(self, monkeypatch):
        """DEEPR_EXPERT_QUICK_TOPICS overrides default."""
        monkeypatch.setenv("DEEPR_EXPERT_QUICK_TOPICS", "20")
        ec = ExpertConfig()
        assert ec.quick_research_topics == 20

    def test_auto_synthesis_from_env(self, monkeypatch):
        """DEEPR_EXPERT_AUTO_SYNTHESIS overrides default."""
        monkeypatch.setenv("DEEPR_EXPERT_AUTO_SYNTHESIS", "false")
        ec = ExpertConfig()
        assert ec.auto_synthesis is False


class TestDatabaseConfig:
    """Test DatabaseConfig Pydantic model."""

    def test_defaults(self):
        """Default values are correct."""
        dc = DatabaseConfig()
        assert dc.type == "jsonl"
        assert dc.jsonl_path == "data/logs/job_log.jsonl"
        assert dc.sqlite_path == "data/logs/jobs.db"

    def test_cosmosdb_fields(self):
        """CosmosDB fields accepted."""
        dc = DatabaseConfig(
            type="cosmosdb",
            cosmosdb_endpoint="https://my.cosmos.azure.com:443/",
            cosmosdb_key="key123",
            cosmosdb_database="mydb",
        )
        assert dc.cosmosdb_endpoint == "https://my.cosmos.azure.com:443/"
        assert dc.cosmosdb_database == "mydb"


class TestAppConfig:
    """Test AppConfig main configuration."""

    def test_defaults(self):
        """Default values are correct."""
        ac = AppConfig()
        assert ac.environment == "local"
        assert ac.debug is False
        assert ac.log_level == "INFO"
        assert isinstance(ac.provider, ProviderConfig)
        assert isinstance(ac.storage, StorageConfig)

    def test_from_env_openai(self, monkeypatch):
        """from_env with OpenAI provider."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("DEEPR_PROVIDER", "openai")
        ac = AppConfig.from_env()
        assert ac.provider.type == "openai"
        assert ac.provider.openai_api_key == "sk-test"

    def test_from_env_azure(self, monkeypatch):
        """from_env with Azure provider."""
        monkeypatch.setenv("DEEPR_PROVIDER", "azure")
        monkeypatch.setenv("AZURE_OPENAI_KEY", "az-key")
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://my.openai.azure.com/")
        ac = AppConfig.from_env()
        assert ac.provider.type == "azure"
        assert ac.provider.azure_api_key == "az-key"

    def test_from_env_defaults(self, monkeypatch):
        """from_env uses defaults when no env vars set."""
        # Clear provider-specific keys
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("DEEPR_PROVIDER", raising=False)
        ac = AppConfig.from_env()
        assert ac.environment == "local"
        assert ac.provider.type == "openai"

    def test_from_env_debug(self, monkeypatch):
        """from_env reads DEEPR_DEBUG."""
        monkeypatch.setenv("DEEPR_DEBUG", "true")
        ac = AppConfig.from_env()
        assert ac.debug is True


class TestAppConfigToEnvFile:
    """Test .env file generation."""

    def test_to_env_file_openai(self, tmp_path):
        """Generates .env with OpenAI configuration."""
        ac = AppConfig(provider=ProviderConfig(type="openai", openai_api_key="sk-test"))
        env_path = str(tmp_path / ".env.example")
        ac.to_env_file(env_path)
        content = (tmp_path / ".env.example").read_text()
        assert "OPENAI_API_KEY=***" in content
        assert "DEEPR_PROVIDER=openai" in content

    def test_to_env_file_azure(self, tmp_path):
        """Generates .env with Azure configuration."""
        ac = AppConfig(
            provider=ProviderConfig(
                type="azure",
                azure_api_key="az-key",
                azure_endpoint="https://my.openai.azure.com/",
            )
        )
        env_path = str(tmp_path / ".env.example")
        ac.to_env_file(env_path)
        content = (tmp_path / ".env.example").read_text()
        assert "AZURE_OPENAI_KEY=***" in content
        assert "DEEPR_PROVIDER=azure" in content


class TestLoadConfig:
    """Test load_config() function."""

    def test_returns_dict(self, monkeypatch):
        """Returns a dictionary."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        result = load_config()
        assert isinstance(result, dict)

    def test_required_keys(self, monkeypatch):
        """Result contains required keys."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        result = load_config()
        for key in [
            "provider",
            "api_key",
            "queue",
            "storage",
            "results_dir",
            "max_cost_per_job",
            "max_daily_cost",
            "max_monthly_cost",
        ]:
            assert key in result

    def test_cost_limits_from_env(self, monkeypatch):
        """Cost limits read from environment variables."""
        monkeypatch.setenv("DEEPR_MAX_COST_PER_JOB", "10.0")
        monkeypatch.setenv("DEEPR_MAX_COST_PER_DAY", "50.0")
        monkeypatch.setenv("DEEPR_MAX_COST_PER_MONTH", "500.0")
        result = load_config()
        assert result["max_cost_per_job"] == 10.0
        assert result["max_daily_cost"] == 50.0
        assert result["max_monthly_cost"] == 500.0


class TestLoadConfigContract:
    """Characterization of deepr.config.load_config() before the Phase Q1.1
    migration to typed get_settings().

    These pin the exact contract the ~53 call sites depend on, so the migration
    cannot silently change the dict's shape, the api-key redaction, or the
    default cost limits. The last test pins the *divergence* from
    deepr.core.settings.load_config() so a blind unification of the two fails
    here deliberately rather than shipping a behavior change. See
    docs/design/code-health.md Q1.1.
    """

    EXPECTED_KEYS = {
        "provider",
        "api_key",
        "azure_endpoint",
        "queue",
        "queue_db_path",
        "storage",
        "results_dir",
        "experts_dir",
        "max_cost_per_job",
        "max_daily_cost",
        "max_monthly_cost",
    }

    def test_exact_key_set(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert set(load_config().keys()) == self.EXPECTED_KEYS

    def test_api_key_is_always_redacted(self, monkeypatch):
        # Security invariant: load_config never exposes a real key. Callers that
        # need the real key fetch it elsewhere and treat "***" as a sentinel
        # (see the comments in context_builder/curriculum/providers). The
        # migration MUST preserve this - get_settings() returns the real key.
        monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-must-not-leak")
        assert load_config()["api_key"] == "***"

    def test_hardcoded_queue_fields(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        result = load_config()
        assert result["queue"] == "local"
        assert result["queue_db_path"] == "queue/research_queue.db"

    def test_default_cost_limits_when_env_unset(self, monkeypatch):
        for var in ("DEEPR_MAX_COST_PER_JOB", "DEEPR_MAX_COST_PER_DAY", "DEEPR_MAX_COST_PER_MONTH"):
            monkeypatch.delenv(var, raising=False)
        result = load_config()
        assert result["max_cost_per_job"] == 5.0
        assert result["max_daily_cost"] == 25.0
        assert result["max_monthly_cost"] == 200.0

    def test_results_dir_honors_reports_path_env(self, monkeypatch):
        monkeypatch.setenv("DEEPR_REPORTS_PATH", "custom/reports/here")
        assert load_config()["results_dir"] == "custom/reports/here"

    def test_diverges_from_settings_load_config(self, monkeypatch):
        # HAZARD pin (Q1.1): the two load_config implementations disagree, so a
        # blind unification must trip this test. config.py redacts api_key and
        # carries experts_dir; core.settings.load_config does neither.
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from deepr.core.settings import get_settings
        from deepr.core.settings import load_config as settings_load_config

        get_settings(reset=True)  # deterministic singleton state
        cfg = load_config()
        settings_cfg = settings_load_config()

        assert cfg["api_key"] == "***"
        assert "experts_dir" in cfg
        assert "experts_dir" not in settings_cfg
        assert settings_cfg["api_key"] != "***"  # settings does not redact


class TestLoadConfigSettingsEquivalence:
    """Q1.1 field-equivalence reconciliation: prove each load_config() value
    equals its get_settings() accessor, so the per-site migration is mechanical
    and behavior-preserving.

    Three fields are knowingly NOT equivalent and are excluded here, each with
    a defined migration path (see test_provider_default_diverges below and the
    Q1.1 notes in docs/design/code-health.md):
      - provider: config reads DEEPR_PROVIDER (default "openai"); Settings reads
        DEEPR_DEFAULT_PROVIDER (default "xai"). This IS consumed - ~13 sites do
        create_provider(config.get("provider", "openai"), ...) - so the
        divergence is a real migration hazard, NOT inert: those sites must
        preserve the "openai" default (or the maintainer deliberately unifies on
        Settings' "xai") rather than blindly switch to default_provider, which
        would flip the provider for every create_provider call.
      - api_key: load_config redacts to "***"; get_settings returns the real
        key (sites reading it migrate with explicit care, not a blind swap).
      - experts_dir: absent from Settings; those sites migrate to experts_root()
        directly, which is the canonical source load_config already wraps.
    """

    EQUIVALENT_KEYS = [
        "azure_endpoint",
        "queue",
        "queue_db_path",
        "storage",
        "results_dir",
        "max_cost_per_job",
        "max_daily_cost",
        "max_monthly_cost",
    ]

    @staticmethod
    def _settings_value(settings, key):
        if key == "azure_endpoint":
            az = settings.providers.get("azure")
            return az.azure_endpoint if az else None
        if key == "queue":
            return "local"
        if key == "queue_db_path":
            return "queue/research_queue.db"
        if key == "storage":
            return settings.storage.type.value
        if key == "results_dir":
            return settings.storage.local_path
        if key == "max_cost_per_job":
            return settings.budget.max_cost_per_job
        if key == "max_daily_cost":
            return settings.budget.daily_limit
        if key == "max_monthly_cost":
            return settings.budget.monthly_limit
        raise KeyError(key)

    def _mismatches(self):
        from deepr.core.settings import get_settings

        settings = get_settings(reset=True)
        cfg = load_config()
        return {
            key: (cfg[key], self._settings_value(settings, key))
            for key in self.EQUIVALENT_KEYS
            if cfg[key] != self._settings_value(settings, key)
        }

    def test_equivalent_under_defaults(self, monkeypatch):
        for var in (
            "DEEPR_PROVIDER",
            "DEEPR_STORAGE",
            "DEEPR_REPORTS_PATH",
            "DEEPR_MAX_COST_PER_JOB",
            "DEEPR_MAX_COST_PER_DAY",
            "DEEPR_MAX_COST_PER_MONTH",
            "DEEPR_DAILY_LIMIT",
            "DEEPR_MONTHLY_LIMIT",
            "AZURE_OPENAI_ENDPOINT",
        ):
            monkeypatch.delenv(var, raising=False)
        assert self._mismatches() == {}

    def test_equivalent_under_overrides(self, monkeypatch):
        monkeypatch.setenv("DEEPR_REPORTS_PATH", "x/y/reports")
        monkeypatch.setenv("DEEPR_MAX_COST_PER_JOB", "7.0")
        monkeypatch.setenv("DEEPR_MAX_COST_PER_DAY", "33.0")
        monkeypatch.setenv("DEEPR_MAX_COST_PER_MONTH", "150.0")
        assert self._mismatches() == {}

    def test_provider_default_diverges(self, monkeypatch):
        # Real, consumed divergence: config.py reads DEEPR_PROVIDER (default
        # "openai"); Settings reads DEEPR_DEFAULT_PROVIDER (default "xai"). ~13
        # sites read config.get("provider", "openai") (pollers, company_research,
        # research/queue/jobs commands) and feed it to create_provider, so a
        # blind migration to get_settings().default_provider would flip those
        # from openai to xai. Provider/api_key sites are the careful bucket.
        monkeypatch.delenv("DEEPR_PROVIDER", raising=False)
        monkeypatch.delenv("DEEPR_DEFAULT_PROVIDER", raising=False)
        from deepr.core.settings import get_settings

        settings = get_settings(reset=True)
        assert load_config()["provider"] == "openai"
        assert settings.default_provider == "xai"
