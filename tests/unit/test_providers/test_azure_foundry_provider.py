"""Tests for Azure AI Foundry provider implementation."""

import os
from unittest.mock import MagicMock, patch

import pytest

from deepr.providers.base import ResearchRequest


class TestAzureFoundryProvider:
    """Test Azure AI Foundry provider."""

    @pytest.fixture
    def mock_azure_modules(self):
        """Mock Azure SDK modules for testing without actual Azure dependencies."""
        mock_project_client_cls = MagicMock()
        mock_agents_client_cls = MagicMock()
        mock_credential_cls = MagicMock()
        mock_deep_research_tool_cls = MagicMock()
        mock_message_role = MagicMock()
        mock_message_role.AGENT = "assistant"

        with (
            patch.dict(
                "sys.modules",
                {
                    "azure": MagicMock(),
                    "azure.ai": MagicMock(),
                    "azure.ai.projects": MagicMock(AIProjectClient=mock_project_client_cls),
                    "azure.ai.agents": MagicMock(AgentsClient=mock_agents_client_cls),
                    "azure.ai.agents.models": MagicMock(
                        DeepResearchTool=mock_deep_research_tool_cls,
                        MessageRole=mock_message_role,
                    ),
                    "azure.identity": MagicMock(DefaultAzureCredential=mock_credential_cls),
                },
            ),
        ):
            yield {
                "project_client_cls": mock_project_client_cls,
                "agents_client_cls": mock_agents_client_cls,
                "credential_cls": mock_credential_cls,
                "deep_research_tool_cls": mock_deep_research_tool_cls,
                "message_role": mock_message_role,
            }

    @pytest.fixture
    def provider(self, mock_azure_modules):
        """Create provider instance for testing."""
        from deepr.providers.azure_foundry_provider import AzureFoundryProvider

        return AzureFoundryProvider(
            project_endpoint="https://test-project.services.ai.azure.com/api/projects/test",
            deep_research_deployment="o3-deep-research",
            gpt_deployment="gpt-4o",
            bing_resource_name="test-bing-connection",
        )

    def test_provider_initialization(self, provider):
        """Test provider initializes correctly."""
        assert provider.project_endpoint == "https://test-project.services.ai.azure.com/api/projects/test"
        assert provider.deep_research_deployment == "o3-deep-research"
        assert provider.gpt_deployment == "gpt-4o"
        assert provider.bing_resource_name == "test-bing-connection"

    def test_provider_initialization_no_endpoint(self, mock_azure_modules):
        """Test provider fails without endpoint."""
        from deepr.providers.azure_foundry_provider import AzureFoundryProvider

        with patch.dict(os.environ, {}, clear=True):
            env_vars_to_clear = ["AZURE_PROJECT_ENDPOINT"]
            for var in env_vars_to_clear:
                os.environ.pop(var, None)

            with pytest.raises(ValueError, match="Azure AI Foundry project endpoint is required"):
                AzureFoundryProvider(project_endpoint=None)

    def test_provider_initialization_from_env(self, mock_azure_modules):
        """Test provider loads config from environment variables."""
        from deepr.providers.azure_foundry_provider import AzureFoundryProvider

        env_vars = {
            "AZURE_PROJECT_ENDPOINT": "https://env-project.services.ai.azure.com/api/projects/env",
            "AZURE_DEEP_RESEARCH_DEPLOYMENT": "o3-custom",
            "AZURE_GPT_DEPLOYMENT": "gpt-4o-custom",
            "AZURE_BING_RESOURCE_NAME": "env-bing",
        }
        with patch.dict(os.environ, env_vars):
            p = AzureFoundryProvider()
            assert p.project_endpoint == "https://env-project.services.ai.azure.com/api/projects/env"
            assert p.deep_research_deployment == "o3-custom"
            assert p.gpt_deployment == "gpt-4o-custom"
            assert p.bing_resource_name == "env-bing"

    def test_model_name_mapping(self, provider):
        """Test model name mapping."""
        assert provider.get_model_name("o3-deep-research") == "o3-deep-research"
        assert provider.get_model_name("gpt-5") == "gpt-5"
        assert provider.get_model_name("gpt-5-mini") == "gpt-5-mini"
        assert provider.get_model_name("gpt-4.1") == "gpt-4o"  # defaults to gpt_deployment
        assert provider.get_model_name("gpt-4.1-mini") == "gpt-4.1-mini"
        assert provider.get_model_name("gpt-4o") == "gpt-4o"
        assert provider.get_model_name("gpt-4o-mini") == "gpt-4o-mini"
        assert provider.get_model_name("unknown-model") == "unknown-model"

    def test_model_name_custom_mappings(self, mock_azure_modules):
        """Test custom model name mappings."""
        from deepr.providers.azure_foundry_provider import AzureFoundryProvider

        p = AzureFoundryProvider(
            project_endpoint="https://test.com",
            model_mappings={"o3-deep-research": "my-custom-deployment"},
        )
        assert p.get_model_name("o3-deep-research") == "my-custom-deployment"

    def test_is_deep_research_model(self, mock_azure_modules):
        """Test _is_deep_research_model detection."""
        from deepr.providers.azure_foundry_provider import _is_deep_research_model

        assert _is_deep_research_model("o3-deep-research") is True
        assert _is_deep_research_model("o3-deep-research-2026-01") is True
        assert _is_deep_research_model("gpt-5") is False
        assert _is_deep_research_model("gpt-5-mini") is False
        assert _is_deep_research_model("gpt-4.1") is False
        assert _is_deep_research_model("gpt-4.1-mini") is False
        assert _is_deep_research_model("gpt-4o") is False
        assert _is_deep_research_model("gpt-4o-mini") is False

    def test_pricing_configuration(self, provider):
        """Test pricing is configured for all regular models."""
        for model in ("gpt-5", "gpt-5-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini"):
            assert model in provider.pricing, f"Missing pricing for {model}"
            assert provider.pricing[model]["input"] > 0
            assert provider.pricing[model]["output"] > 0

    def test_calculate_cost_regular(self, provider):
        """Test cost calculation for regular models."""
        cost = provider._calculate_cost(1000, 1000, "gpt-4o-mini")
        assert cost > 0
        # gpt-4o-mini: $0.15/M input + $0.60/M output
        # 1000 tokens = 0.001M -> $0.00015 + $0.0006 = $0.00075
        assert abs(cost - 0.00075) < 0.0001

    def test_calculate_cost_deep_research(self, provider):
        """Test cost calculation returns flat estimate for deep research."""
        cost = provider._calculate_cost(1000, 1000, "o3-deep-research")
        assert cost == 0.50

    # =========================================================================
    # Deep research mode tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_submit_deep_research(self, provider, mock_azure_modules):
        """Test submitting a deep research job."""
        mock_agents = MagicMock()
        mock_thread = MagicMock()
        mock_thread.id = "thread-123"
        mock_run = MagicMock()
        mock_run.id = "run-456"

        mock_agents.threads.create.return_value = mock_thread
        mock_agents.messages.create.return_value = MagicMock()
        mock_agents.runs.create.return_value = mock_run
        mock_agents.create_agent.return_value = MagicMock(id="agent-789")

        provider._agents_client = mock_agents

        mock_tool = MagicMock()
        mock_tool.definitions = [{"type": "deep_research"}]
        mock_azure_modules["deep_research_tool_cls"].return_value = mock_tool

        request = ResearchRequest(
            prompt="What are the latest trends in AI?",
            model="o3-deep-research",
            system_message="You are a research assistant.",
        )

        job_id = await provider.submit_research(request)

        assert job_id == "thread-123:run-456"
        assert job_id in provider._jobs
        assert provider._jobs[job_id]["status"] == "in_progress"
        assert provider._jobs[job_id]["kind"] == "deep_research"
        assert provider._jobs[job_id]["thread_id"] == "thread-123"
        assert provider._jobs[job_id]["run_id"] == "run-456"

    @pytest.mark.asyncio
    async def test_get_status_deep_research_completed(self, provider, mock_azure_modules):
        """Test get_status for completed deep research with citations."""
        provider._jobs["thread-2:run-2"] = {
            "status": "in_progress",
            "kind": "deep_research",
            "thread_id": "thread-2",
            "run_id": "run-2",
            "created_at": None,
            "model": "o3-deep-research",
        }

        mock_agents = MagicMock()
        mock_run = MagicMock()
        mock_run.status = "completed"
        mock_run.usage = None
        mock_agents.runs.get.return_value = mock_run

        mock_text_msg = MagicMock()
        mock_text_msg.text.value = "Research findings about AI trends."

        mock_citation = MagicMock()
        mock_citation.url_citation.title = "AI Report 2026"
        mock_citation.url_citation.url = "https://example.com/ai-report"

        mock_last_msg = MagicMock()
        mock_last_msg.text_messages = [mock_text_msg]
        mock_last_msg.url_citation_annotations = [mock_citation]

        mock_agents.messages.get_last_message_by_role.return_value = mock_last_msg
        provider._agents_client = mock_agents

        response = await provider.get_status("thread-2:run-2")

        assert response.status == "completed"
        assert response.output is not None
        assert "Research findings about AI trends." in response.output[0]["content"][0]["text"]
        assert response.metadata["citations"][0]["url"] == "https://example.com/ai-report"
        assert response.usage is not None
        assert response.usage.cost >= 0.50  # Deep research base cost

    # =========================================================================
    # Regular mode tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_submit_regular_research(self, provider, mock_azure_modules):
        """Test submitting a regular (non-deep-research) job."""
        mock_agents = MagicMock()
        mock_thread = MagicMock()
        mock_thread.id = "thread-reg-1"
        mock_run = MagicMock()
        mock_run.id = "run-reg-1"

        mock_agents.threads.create.return_value = mock_thread
        mock_agents.messages.create.return_value = MagicMock()
        mock_agents.runs.create.return_value = mock_run
        mock_agents.create_agent.return_value = MagicMock(id="agent-reg-1")

        provider._agents_client = mock_agents

        request = ResearchRequest(
            prompt="What is the latest on EU AI Act enforcement?",
            model="gpt-4o",
            system_message="You are a helpful assistant.",
        )

        job_id = await provider.submit_research(request)

        assert job_id == "thread-reg-1:run-reg-1"
        assert provider._jobs[job_id]["kind"] == "regular"
        assert provider._jobs[job_id]["model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_submit_regular_gpt4o_mini(self, provider, mock_azure_modules):
        """Test submitting a gpt-4o-mini job."""
        mock_agents = MagicMock()
        mock_thread = MagicMock()
        mock_thread.id = "thread-mini-1"
        mock_run = MagicMock()
        mock_run.id = "run-mini-1"

        mock_agents.threads.create.return_value = mock_thread
        mock_agents.messages.create.return_value = MagicMock()
        mock_agents.runs.create.return_value = mock_run
        mock_agents.create_agent.return_value = MagicMock(id="agent-mini-1")

        provider._agents_client = mock_agents

        request = ResearchRequest(
            prompt="Summarize this briefly",
            model="gpt-4o-mini",
            system_message="",
        )

        job_id = await provider.submit_research(request)

        assert provider._jobs[job_id]["kind"] == "regular"
        assert provider._jobs[job_id]["model"] == "gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_get_status_regular_completed(self, provider, mock_azure_modules):
        """Test get_status for completed regular job with token usage."""
        provider._jobs["thread-r:run-r"] = {
            "status": "in_progress",
            "kind": "regular",
            "thread_id": "thread-r",
            "run_id": "run-r",
            "created_at": None,
            "model": "gpt-4o",
        }

        mock_agents = MagicMock()
        mock_run = MagicMock()
        mock_run.status = "completed"
        mock_run.usage = MagicMock()
        mock_run.usage.prompt_tokens = 500
        mock_run.usage.completion_tokens = 1000
        mock_agents.runs.get.return_value = mock_run

        mock_text_msg = MagicMock()
        mock_text_msg.text.value = "The EU AI Act is being enforced in phases."

        mock_last_msg = MagicMock()
        mock_last_msg.text_messages = [mock_text_msg]
        mock_last_msg.url_citation_annotations = []

        mock_agents.messages.get_last_message_by_role.return_value = mock_last_msg
        provider._agents_client = mock_agents

        response = await provider.get_status("thread-r:run-r")

        assert response.status == "completed"
        assert response.model == "gpt-4o"
        assert response.usage is not None
        assert response.usage.input_tokens == 500
        assert response.usage.output_tokens == 1000
        assert response.usage.cost > 0
        # No citations for regular jobs
        assert response.metadata["citations"] == []

    # =========================================================================
    # Shared tests (both modes)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_status_in_progress(self, provider, mock_azure_modules):
        """Test get_status when job is still in progress."""
        provider._jobs["thread-1:run-1"] = {
            "status": "in_progress",
            "kind": "deep_research",
            "thread_id": "thread-1",
            "run_id": "run-1",
            "created_at": None,
            "model": "o3-deep-research",
        }

        mock_agents = MagicMock()
        mock_run = MagicMock()
        mock_run.status = "in_progress"
        mock_agents.runs.get.return_value = mock_run
        provider._agents_client = mock_agents

        response = await provider.get_status("thread-1:run-1")

        assert response.id == "thread-1:run-1"
        assert response.status == "in_progress"

    @pytest.mark.asyncio
    async def test_get_status_failed(self, provider, mock_azure_modules):
        """Test get_status when job has failed."""
        provider._jobs["thread-3:run-3"] = {
            "status": "in_progress",
            "kind": "regular",
            "thread_id": "thread-3",
            "run_id": "run-3",
            "created_at": None,
            "model": "gpt-4o",
        }

        mock_agents = MagicMock()
        mock_run = MagicMock()
        mock_run.status = "failed"
        mock_run.last_error = MagicMock()
        mock_run.last_error.message = "Rate limit exceeded"
        mock_agents.runs.get.return_value = mock_run
        provider._agents_client = mock_agents

        response = await provider.get_status("thread-3:run-3")

        assert response.status == "failed"
        assert response.error == "Rate limit exceeded"

    @pytest.mark.asyncio
    async def test_get_status_not_found(self, provider):
        """Test get_status raises for unknown job ID."""
        from deepr.providers.base import ProviderError

        with pytest.raises(ProviderError, match="Job unknown-id not found"):
            await provider.get_status("unknown-id")

    @pytest.mark.asyncio
    async def test_get_status_cached_completed(self, provider):
        """Test get_status returns cached result for completed jobs."""
        provider._jobs["thread-4:run-4"] = {
            "status": "completed",
            "kind": "regular",
            "thread_id": "thread-4",
            "run_id": "run-4",
            "created_at": None,
            "completed_at": None,
            "model": "gpt-4o",
            "output": "Cached result",
            "citations": [],
            "estimated_cost": 0.03,
            "usage": {"prompt_tokens": 100, "completion_tokens": 200},
        }

        response = await provider.get_status("thread-4:run-4")
        assert response.status == "completed"

    @pytest.mark.asyncio
    async def test_cancel_job(self, provider, mock_azure_modules):
        """Test cancelling a running job."""
        provider._jobs["thread-5:run-5"] = {
            "status": "in_progress",
            "thread_id": "thread-5",
            "run_id": "run-5",
            "created_at": None,
            "model": "o3-deep-research",
        }

        mock_agents = MagicMock()
        mock_agents.runs.cancel.return_value = None
        provider._agents_client = mock_agents

        result = await provider.cancel_job("thread-5:run-5")

        assert result is True
        assert provider._jobs["thread-5:run-5"]["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_completed_job(self, provider):
        """Test cancelling an already completed job returns False."""
        provider._jobs["thread-6:run-6"] = {
            "status": "completed",
            "thread_id": "thread-6",
            "run_id": "run-6",
            "created_at": None,
            "model": "o3-deep-research",
        }

        result = await provider.cancel_job("thread-6:run-6")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_unknown_job(self, provider):
        """Test cancelling an unknown job returns False."""
        result = await provider.cancel_job("unknown-job")
        assert result is False

    @pytest.mark.asyncio
    async def test_upload_document_not_supported(self, provider):
        """Test upload_document raises ProviderError."""
        from deepr.providers.base import ProviderError

        with pytest.raises(ProviderError, match="does not support standalone file uploads"):
            await provider.upload_document("/tmp/test.pdf")

    @pytest.mark.asyncio
    async def test_create_vector_store_not_supported(self, provider):
        """Test create_vector_store raises ProviderError."""
        from deepr.providers.base import ProviderError

        with pytest.raises(ProviderError, match="does not support vector stores"):
            await provider.create_vector_store("test-store", ["file-1"])

    @pytest.mark.asyncio
    async def test_list_vector_stores_empty(self, provider):
        """Test list_vector_stores returns empty list."""
        result = await provider.list_vector_stores()
        assert result == []

    @pytest.mark.asyncio
    async def test_wait_for_vector_store_returns_false(self, provider):
        """Test wait_for_vector_store returns False."""
        result = await provider.wait_for_vector_store("vs-id")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_vector_store_returns_false(self, provider):
        """Test delete_vector_store returns False."""
        result = await provider.delete_vector_store("vs-id")
        assert result is False

    def test_poll_interval_early(self, provider):
        """Test polling interval for early stages."""
        assert provider.get_poll_interval(10) == 5.0
        assert provider.get_poll_interval(29) == 5.0

    def test_poll_interval_mid(self, provider):
        """Test polling interval for mid stages."""
        assert provider.get_poll_interval(30) == 10.0
        assert provider.get_poll_interval(60) == 10.0
        assert provider.get_poll_interval(119) == 10.0

    def test_poll_interval_late(self, provider):
        """Test polling interval for late stages."""
        assert provider.get_poll_interval(120) == 20.0
        assert provider.get_poll_interval(300) == 20.0

    def test_cost_estimation_from_citations(self, provider):
        """Test cost estimation based on citation/search count."""
        # With few citations, base cost wins
        estimated = max(provider.deep_research_cost_estimate, 3 * 0.035)
        assert estimated == 0.50

        # With many citations, search cost wins
        estimated = max(provider.deep_research_cost_estimate, 20 * 0.035)
        assert estimated == 0.70

    def test_close_deletes_all_agents(self, provider, mock_azure_modules):
        """Test close() deletes both deep research and regular agents."""
        mock_agents = MagicMock()
        provider._agents_client = mock_agents
        provider._deep_research_agent_id = "dr-agent"
        provider._regular_agent_ids = {"gpt-4o": "reg-agent-1", "gpt-4o-mini": "reg-agent-2"}

        provider.close()

        assert mock_agents.delete_agent.call_count == 3
        mock_agents.delete_agent.assert_any_call("dr-agent")
        mock_agents.delete_agent.assert_any_call("reg-agent-1")
        mock_agents.delete_agent.assert_any_call("reg-agent-2")
        assert provider._deep_research_agent_id is None
        assert provider._regular_agent_ids == {}

    def test_close_no_agent(self, provider):
        """Test close() with no agents is a no-op."""
        provider._deep_research_agent_id = None
        provider._regular_agent_ids = {}
        provider.close()  # Should not raise


class TestAzureFoundryProviderRegistration:
    """Test Azure Foundry provider is correctly registered."""

    def test_provider_type_includes_azure_foundry(self):
        """Test ProviderType includes azure-foundry."""
        from deepr.providers import ProviderType

        assert "azure-foundry" in ProviderType.__args__

    def test_create_provider_azure_foundry_import_error(self):
        """Test create_provider raises ImportError when SDK not installed."""
        from deepr.providers import create_provider

        with patch("deepr.providers.AzureFoundryProvider", None):
            with pytest.raises(ImportError, match="Azure Foundry provider requires"):
                create_provider("azure-foundry")

    def test_model_capabilities_registered(self):
        """Test all azure-foundry models are in the registry."""
        from deepr.providers.registry import MODEL_CAPABILITIES

        expected_models = {
            "azure-foundry/o3-deep-research": 0.50,
            "azure-foundry/gpt-5": 0.15,
            "azure-foundry/gpt-5-mini": 0.03,
            "azure-foundry/gpt-4.1": 0.04,
            "azure-foundry/gpt-4.1-mini": 0.01,
            "azure-foundry/gpt-4o": 0.03,
            "azure-foundry/gpt-4o-mini": 0.005,
        }
        for key, expected_cost in expected_models.items():
            assert key in MODEL_CAPABILITIES, f"Missing registry entry: {key}"
            cap = MODEL_CAPABILITIES[key]
            assert cap.provider == "azure-foundry"
            assert cap.cost_per_query == expected_cost, f"{key} cost mismatch"

    def test_auto_mode_cost_entries(self):
        """Test all azure-foundry models in auto mode cost table."""
        from deepr.routing.auto_mode import MODEL_COSTS

        expected = [
            ("azure-foundry", "o3-deep-research"),
            ("azure-foundry", "gpt-5"),
            ("azure-foundry", "gpt-5-mini"),
            ("azure-foundry", "gpt-4.1"),
            ("azure-foundry", "gpt-4.1-mini"),
            ("azure-foundry", "gpt-4o"),
            ("azure-foundry", "gpt-4o-mini"),
        ]
        for key in expected:
            assert key in MODEL_COSTS, f"Missing auto_mode cost entry: {key}"

    def test_auto_mode_env_mapping(self):
        """Test azure-foundry has env var mapping."""
        from deepr.routing.auto_mode import _PROVIDER_KEY_ENV

        assert "azure-foundry" in _PROVIDER_KEY_ENV
        assert _PROVIDER_KEY_ENV["azure-foundry"] == "AZURE_PROJECT_ENDPOINT"

    def test_provider_factory_key_map(self):
        """Test provider factory has azure-foundry key mapping."""
        from deepr.cli.commands.provider_factory import supports_background_jobs

        assert supports_background_jobs("azure-foundry") is True

    def test_supports_vector_stores_excludes_foundry(self):
        """Test vector stores correctly excludes azure-foundry."""
        from deepr.cli.commands.provider_factory import supports_vector_stores

        assert supports_vector_stores("azure-foundry") is False
