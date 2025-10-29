"""Tests for OpenAI provider implementation."""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from deepr.providers import OpenAIProvider
from deepr.providers.base import ResearchRequest, ToolConfig


@pytest.mark.asyncio
class TestOpenAIProvider:
    """Test OpenAI provider."""

    @pytest.fixture
    def provider(self):
        """Create provider instance for testing."""
        return OpenAIProvider(api_key="sk-test-key")

    def test_provider_initialization(self, provider):
        """Test provider initializes correctly."""
        assert provider.api_key == "sk-test-key"
        assert provider.client is not None
        assert "o3-deep-research" in provider.model_mappings

    def test_model_name_mapping(self, provider):
        """Test model name mapping."""
        assert provider.get_model_name("o3-deep-research") == "o3-deep-research-2025-06-26"
        assert provider.get_model_name("o4-mini-deep-research") == "o4-mini-deep-research"
        assert provider.get_model_name("unknown-model") == "unknown-model"

    @pytest.mark.asyncio
    async def test_submit_research(self, provider):
        """Test research submission (mocked)."""
        mock_response = MagicMock()
        mock_response.id = "resp_test123"

        with patch.object(provider.client.responses, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response

            request = ResearchRequest(
                prompt="Test prompt",
                model="o3-deep-research",
                system_message="Test system message",
                tools=[ToolConfig(type="web_search_preview")],
                metadata={"test": "value"},
            )

            job_id = await provider.submit_research(request)

            assert job_id == "resp_test123"
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_status(self, provider):
        """Test job status retrieval (mocked)."""
        mock_response = MagicMock()
        mock_response.id = "resp_test123"
        mock_response.status = "completed"
        mock_response.model = "o3-deep-research"
        mock_response.usage = None
        mock_response.output = []

        with patch.object(provider.client.responses, "retrieve", new_callable=AsyncMock) as mock_retrieve:
            mock_retrieve.return_value = mock_response

            status = await provider.get_status("resp_test123")

            assert status.id == "resp_test123"
            assert status.status == "completed"
            mock_retrieve.assert_called_once_with("resp_test123")

    @pytest.mark.asyncio
    async def test_cancel_job(self, provider):
        """Test job cancellation (mocked)."""
        with patch.object(provider.client.responses, "cancel", new_callable=AsyncMock) as mock_cancel:
            mock_cancel.return_value = None

            success = await provider.cancel_job("resp_test123")

            assert success is True
            mock_cancel.assert_called_once_with("resp_test123")

    @pytest.mark.asyncio
    async def test_upload_document(self, provider, tmp_path):
        """Test document upload (mocked)."""
        # Create temporary file
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        mock_file_obj = MagicMock()
        mock_file_obj.id = "file_test123"

        with patch.object(provider.client.files, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_file_obj

            file_id = await provider.upload_document(str(test_file))

            assert file_id == "file_test123"
            mock_create.assert_called_once()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set"
)
class TestOpenAIProviderIntegration:
    """Integration tests with real OpenAI API (requires API key)."""

    @pytest.fixture
    def provider(self):
        """Create real provider instance."""
        return OpenAIProvider(api_key=os.getenv("OPENAI_API_KEY"))

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.requires_api
    @pytest.mark.skip(reason="Costs money - run explicitly with: pytest -m 'requires_api'")
    async def test_real_research_submission(self, provider):
        """Test real research submission (short, cheap query).

        COSTS ~$0.10 - Only run when explicitly testing real API.
        Run with: pytest -m 'requires_api' tests/unit/test_providers/test_openai_provider.py
        """
        from deepr.providers.base import Tool

        request = ResearchRequest(
            prompt="What is 2+2? Answer in one word.",
            model="o4-mini-deep-research",  # Use cheaper model
            system_message="You are a calculator. Answer concisely.",
            tools=[Tool(type="web_search_preview")],  # Required for deep research models
            metadata={"test": "integration"},
        )

        job_id = await provider.submit_research(request)

        assert job_id.startswith("resp_")

        # Check status immediately (will be queued or processing)
        status = await provider.get_status(job_id)

        assert status.status in ["queued", "in_progress", "completed"]

        # Note: Not waiting for completion to keep test fast
        # In real integration tests, you'd poll for completion
