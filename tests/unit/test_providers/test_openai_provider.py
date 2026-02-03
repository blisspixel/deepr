"""Tests for OpenAI provider implementation.

Tests the OpenAI provider covering:
- Request construction (payload building)
- Response parsing (status, usage stats)
- Error handling (retry logic, error scenarios)

Feature: code-quality-security-hardening
**Validates: Requirements 5.1**
"""

import os
import openai
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from deepr.providers import OpenAIProvider
from deepr.providers.base import ResearchRequest, ToolConfig, ProviderError


@pytest.mark.asyncio
class TestOpenAIProvider:
    """Test OpenAI provider.
    
    **Validates: Requirements 5.1**
    """

    @pytest.fixture
    def provider(self):
        """Create provider instance for testing."""
        return OpenAIProvider(api_key="sk-test-key")

    def test_provider_initialization(self, provider):
        """Test provider initializes correctly."""
        assert provider.api_key == "sk-test-key"
        assert provider.client is not None
        assert "o3-deep-research" in provider.model_mappings

    def test_provider_initialization_requires_api_key(self):
        """Test provider raises error without API key."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove OPENAI_API_KEY from environment
            with patch.object(os, 'getenv', return_value=None):
                with pytest.raises(ValueError, match="API key is required"):
                    OpenAIProvider(api_key=None)

    def test_provider_initialization_with_custom_mappings(self):
        """Test provider accepts custom model mappings."""
        custom_mappings = {"custom-model": "custom-model-v1"}
        provider = OpenAIProvider(api_key="sk-test-key", model_mappings=custom_mappings)
        assert provider.get_model_name("custom-model") == "custom-model-v1"

    def test_model_name_mapping(self, provider):
        """Test model name mapping."""
        assert provider.get_model_name("o3-deep-research") == "o3-deep-research-2025-06-26"
        assert provider.get_model_name("o4-mini-deep-research") == "o4-mini-deep-research"
        assert provider.get_model_name("unknown-model") == "unknown-model"

    def test_model_name_mapping_all_aliases(self, provider):
        """Test all model aliases are mapped correctly."""
        assert provider.get_model_name("o3") == "o3-deep-research-2025-06-26"
        assert provider.get_model_name("o4-mini") == "o4-mini-deep-research"


# =============================================================================
# Request Construction Tests
# =============================================================================

@pytest.mark.asyncio
class TestRequestConstruction:
    """Test request payload construction.
    
    **Validates: Requirements 5.1**
    """

    @pytest.fixture
    def provider(self):
        """Create provider instance for testing."""
        return OpenAIProvider(api_key="sk-test-key")

    @pytest.mark.asyncio
    async def test_submit_research_basic_payload(self, provider):
        """Test basic research submission payload construction."""
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
            
            # Verify payload structure
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["model"] == "o3-deep-research-2025-06-26"
            assert call_kwargs["metadata"] == {"test": "value"}
            assert call_kwargs["store"] is True
            assert call_kwargs["background"] is True

    @pytest.mark.asyncio
    async def test_submit_research_with_web_search_tool(self, provider):
        """Test payload includes web_search_preview tool correctly."""
        mock_response = MagicMock()
        mock_response.id = "resp_test123"

        with patch.object(provider.client.responses, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response

            request = ResearchRequest(
                prompt="Test prompt",
                model="o4-mini-deep-research",
                system_message="Test system",
                tools=[ToolConfig(type="web_search_preview")],
            )

            await provider.submit_research(request)
            
            call_kwargs = mock_create.call_args[1]
            tools = call_kwargs["tools"]
            assert len(tools) == 1
            assert tools[0]["type"] == "web_search_preview"

    @pytest.mark.asyncio
    async def test_submit_research_with_code_interpreter_tool(self, provider):
        """Test payload includes code_interpreter tool with container."""
        mock_response = MagicMock()
        mock_response.id = "resp_test123"

        with patch.object(provider.client.responses, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response

            request = ResearchRequest(
                prompt="Test prompt",
                model="o4-mini-deep-research",
                system_message="Test system",
                tools=[ToolConfig(type="code_interpreter")],
            )

            await provider.submit_research(request)
            
            call_kwargs = mock_create.call_args[1]
            tools = call_kwargs["tools"]
            assert len(tools) == 1
            assert tools[0]["type"] == "code_interpreter"
            assert tools[0]["container"] == {"type": "auto"}

    @pytest.mark.asyncio
    async def test_submit_research_with_file_search_tool(self, provider):
        """Test payload includes file_search tool with vector store IDs."""
        mock_response = MagicMock()
        mock_response.id = "resp_test123"

        with patch.object(provider.client.responses, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response

            request = ResearchRequest(
                prompt="Test prompt",
                model="o4-mini-deep-research",
                system_message="Test system",
                tools=[ToolConfig(type="file_search", vector_store_ids=["vs_123", "vs_456"])],
            )

            await provider.submit_research(request)
            
            call_kwargs = mock_create.call_args[1]
            tools = call_kwargs["tools"]
            assert len(tools) == 1
            assert tools[0]["type"] == "file_search"
            assert tools[0]["vector_store_ids"] == ["vs_123", "vs_456"]

    @pytest.mark.asyncio
    async def test_submit_research_with_reasoning_effort(self, provider):
        """Test payload includes reasoning parameters for o-series models."""
        mock_response = MagicMock()
        mock_response.id = "resp_test123"

        with patch.object(provider.client.responses, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response

            request = ResearchRequest(
                prompt="Test prompt",
                model="o3-deep-research",
                system_message="Test system",
                tools=[],
                reasoning_effort="high",
            )

            await provider.submit_research(request)
            
            call_kwargs = mock_create.call_args[1]
            assert "reasoning" in call_kwargs
            assert call_kwargs["reasoning"]["effort"] == "high"
            assert call_kwargs["reasoning"]["summary"] == "auto"

    @pytest.mark.asyncio
    async def test_submit_research_input_message_structure(self, provider):
        """Test input messages are structured correctly."""
        mock_response = MagicMock()
        mock_response.id = "resp_test123"

        with patch.object(provider.client.responses, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response

            request = ResearchRequest(
                prompt="User question",
                model="o4-mini-deep-research",
                system_message="System instructions",
                tools=[],
            )

            await provider.submit_research(request)
            
            call_kwargs = mock_create.call_args[1]
            input_messages = call_kwargs["input"]
            
            # First message should be developer/system
            assert input_messages[0]["role"] == "developer"
            assert input_messages[0]["content"][0]["type"] == "input_text"
            assert input_messages[0]["content"][0]["text"] == "System instructions"
            
            # Second message should be user
            assert input_messages[1]["role"] == "user"
            assert input_messages[1]["content"][0]["type"] == "input_text"
            assert input_messages[1]["content"][0]["text"] == "User question"

    @pytest.mark.asyncio
    async def test_submit_research_with_previous_response_id(self, provider):
        """Test payload includes previous_response_id for reasoning persistence."""
        mock_response = MagicMock()
        mock_response.id = "resp_test123"

        with patch.object(provider.client.responses, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response

            request = ResearchRequest(
                prompt="Follow-up question",
                model="o4-mini-deep-research",
                system_message="Test system",
                tools=[],
                previous_response_id="resp_previous123",
            )

            await provider.submit_research(request)
            
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["previous_response_id"] == "resp_previous123"


# =============================================================================
# Response Parsing Tests
# =============================================================================

@pytest.mark.asyncio
class TestResponseParsing:
    """Test response parsing from OpenAI API.
    
    **Validates: Requirements 5.1**
    """

    @pytest.fixture
    def provider(self):
        """Create provider instance for testing."""
        return OpenAIProvider(api_key="sk-test-key")

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
        mock_response.created_at = None
        mock_response.completed_at = None
        mock_response.metadata = None
        mock_response.error = None

        with patch.object(provider.client.responses, "retrieve", new_callable=AsyncMock) as mock_retrieve:
            mock_retrieve.return_value = mock_response

            status = await provider.get_status("resp_test123")

            assert status.id == "resp_test123"
            assert status.status == "completed"
            mock_retrieve.assert_called_once_with("resp_test123")

    @pytest.mark.asyncio
    async def test_get_status_with_usage_stats(self, provider):
        """Test job status retrieval with usage statistics."""
        mock_usage = MagicMock()
        mock_usage.input_tokens = 1000
        mock_usage.output_tokens = 500
        mock_usage.total_tokens = 1500
        mock_usage.reasoning_tokens = 200
        
        mock_response = MagicMock()
        mock_response.id = "resp_test123"
        mock_response.status = "completed"
        mock_response.model = "o4-mini-deep-research-2025-06-26"
        mock_response.usage = mock_usage
        mock_response.output = []
        mock_response.created_at = 1704067200  # Unix timestamp
        mock_response.completed_at = 1704067260
        mock_response.metadata = {"task": "research"}
        mock_response.error = None

        with patch.object(provider.client.responses, "retrieve", new_callable=AsyncMock) as mock_retrieve:
            mock_retrieve.return_value = mock_response

            status = await provider.get_status("resp_test123")

            assert status.id == "resp_test123"
            assert status.status == "completed"
            assert status.usage is not None
            assert status.usage.input_tokens == 1000
            assert status.usage.output_tokens == 500
            assert status.usage.total_tokens == 1500
            assert status.usage.reasoning_tokens == 200
            assert status.usage.cost > 0  # Cost should be calculated
            assert status.created_at is not None
            assert status.completed_at is not None
            assert status.metadata == {"task": "research"}

    @pytest.mark.asyncio
    async def test_get_status_with_output_content(self, provider):
        """Test job status retrieval with output content parsing."""
        # Create mock output blocks
        mock_text_item = MagicMock()
        mock_text_item.type = "text"
        mock_text_item.text = "Research findings..."
        
        mock_output_block = MagicMock()
        mock_output_block.type = "message"
        mock_output_block.content = [mock_text_item]
        
        mock_response = MagicMock()
        mock_response.id = "resp_test123"
        mock_response.status = "completed"
        mock_response.model = "o4-mini-deep-research"
        mock_response.usage = None
        mock_response.output = [mock_output_block]
        mock_response.created_at = None
        mock_response.completed_at = None
        mock_response.metadata = None
        mock_response.error = None

        with patch.object(provider.client.responses, "retrieve", new_callable=AsyncMock) as mock_retrieve:
            mock_retrieve.return_value = mock_response

            status = await provider.get_status("resp_test123")

            assert status.output is not None
            assert len(status.output) == 1
            assert status.output[0]["type"] == "message"
            assert len(status.output[0]["content"]) == 1
            assert status.output[0]["content"][0]["text"] == "Research findings..."

    @pytest.mark.asyncio
    async def test_get_status_queued(self, provider):
        """Test job status retrieval for queued job."""
        mock_response = MagicMock()
        mock_response.id = "resp_test123"
        mock_response.status = "queued"
        mock_response.model = "o4-mini-deep-research"
        mock_response.usage = None
        mock_response.output = None
        mock_response.created_at = 1704067200
        mock_response.completed_at = None
        mock_response.metadata = None
        mock_response.error = None

        with patch.object(provider.client.responses, "retrieve", new_callable=AsyncMock) as mock_retrieve:
            mock_retrieve.return_value = mock_response

            status = await provider.get_status("resp_test123")

            assert status.status == "queued"
            assert status.output is None
            assert status.completed_at is None

    @pytest.mark.asyncio
    async def test_get_status_failed_with_error(self, provider):
        """Test job status retrieval for failed job with error message."""
        mock_response = MagicMock()
        mock_response.id = "resp_test123"
        mock_response.status = "failed"
        mock_response.model = "o4-mini-deep-research"
        mock_response.usage = None
        mock_response.output = None
        mock_response.created_at = 1704067200
        mock_response.completed_at = None
        mock_response.metadata = None
        mock_response.error = "Rate limit exceeded"

        with patch.object(provider.client.responses, "retrieve", new_callable=AsyncMock) as mock_retrieve:
            mock_retrieve.return_value = mock_response

            status = await provider.get_status("resp_test123")

            assert status.status == "failed"
            assert status.error == "Rate limit exceeded"


# =============================================================================
# Error Handling Tests
# =============================================================================

@pytest.mark.asyncio
class TestErrorHandling:
    """Test error handling and retry logic.
    
    **Validates: Requirements 5.1**
    """

    @pytest.fixture
    def provider(self):
        """Create provider instance for testing."""
        return OpenAIProvider(api_key="sk-test-key")

    @pytest.mark.asyncio
    async def test_submit_research_retries_on_rate_limit(self, provider):
        """Test that rate limit errors trigger retry."""
        from openai import RateLimitError
        
        mock_response = MagicMock()
        mock_response.id = "resp_test123"
        
        # First call raises RateLimitError, second succeeds
        with patch.object(provider.client.responses, "create", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = [
                RateLimitError("Rate limit exceeded", response=MagicMock(), body=None),
                mock_response
            ]
            
            request = ResearchRequest(
                prompt="Test prompt",
                model="o4-mini-deep-research",
                system_message="Test system",
                tools=[],
            )
            
            # Should succeed after retry
            job_id = await provider.submit_research(request)
            assert job_id == "resp_test123"
            assert mock_create.call_count == 2

    @pytest.mark.asyncio
    async def test_submit_research_retries_on_connection_error(self, provider):
        """Test that connection errors trigger retry."""
        from openai import APIConnectionError
        
        mock_response = MagicMock()
        mock_response.id = "resp_test123"
        
        with patch.object(provider.client.responses, "create", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = [
                APIConnectionError(request=MagicMock()),
                mock_response
            ]
            
            request = ResearchRequest(
                prompt="Test prompt",
                model="o4-mini-deep-research",
                system_message="Test system",
                tools=[],
            )
            
            job_id = await provider.submit_research(request)
            assert job_id == "resp_test123"
            assert mock_create.call_count == 2

    @pytest.mark.asyncio
    async def test_submit_research_retries_on_timeout(self, provider):
        """Test that timeout errors trigger retry."""
        from openai import APITimeoutError
        
        mock_response = MagicMock()
        mock_response.id = "resp_test123"
        
        with patch.object(provider.client.responses, "create", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = [
                APITimeoutError(request=MagicMock()),
                mock_response
            ]
            
            request = ResearchRequest(
                prompt="Test prompt",
                model="o4-mini-deep-research",
                system_message="Test system",
                tools=[],
            )
            
            job_id = await provider.submit_research(request)
            assert job_id == "resp_test123"
            assert mock_create.call_count == 2

    @pytest.mark.asyncio
    async def test_submit_research_raises_after_max_retries(self, provider):
        """Test that ProviderError is raised after max retries."""
        from openai import RateLimitError
        
        with patch.object(provider.client.responses, "create", new_callable=AsyncMock) as mock_create:
            # All calls fail
            mock_create.side_effect = RateLimitError(
                "Rate limit exceeded", response=MagicMock(), body=None
            )
            
            request = ResearchRequest(
                prompt="Test prompt",
                model="o4-mini-deep-research",
                system_message="Test system",
                tools=[],
            )
            
            # The provider raises ProviderError after exhausting retries
            with pytest.raises(ProviderError):
                await provider.submit_research(request)

    @pytest.mark.asyncio
    async def test_submit_research_non_retryable_error(self, provider):
        """Test that non-retryable errors raise immediately."""
        with patch.object(provider.client.responses, "create", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = openai.OpenAIError("Invalid parameter")
            
            request = ResearchRequest(
                prompt="Test prompt",
                model="o4-mini-deep-research",
                system_message="Test system",
                tools=[],
            )
            
            with pytest.raises(ProviderError, match="Failed to submit research"):
                await provider.submit_research(request)
            
            # Should not retry for non-retryable errors
            assert mock_create.call_count == 1

    @pytest.mark.asyncio
    async def test_get_status_raises_provider_error(self, provider):
        """Test that get_status raises ProviderError on failure."""
        with patch.object(provider.client.responses, "retrieve", new_callable=AsyncMock) as mock_retrieve:
            mock_retrieve.side_effect = openai.OpenAIError("API error")
            
            with pytest.raises(ProviderError, match="Failed to get status"):
                await provider.get_status("resp_test123")

    @pytest.mark.asyncio
    async def test_cancel_job(self, provider):
        """Test job cancellation (mocked)."""
        with patch.object(provider.client.responses, "cancel", new_callable=AsyncMock) as mock_cancel:
            mock_cancel.return_value = None

            success = await provider.cancel_job("resp_test123")

            assert success is True
            mock_cancel.assert_called_once_with("resp_test123")

    @pytest.mark.asyncio
    async def test_cancel_job_raises_provider_error(self, provider):
        """Test that cancel_job raises ProviderError on failure."""
        with patch.object(provider.client.responses, "cancel", new_callable=AsyncMock) as mock_cancel:
            mock_cancel.side_effect = openai.OpenAIError("Cancel failed")
            
            with pytest.raises(ProviderError, match="Failed to cancel job"):
                await provider.cancel_job("resp_test123")


# =============================================================================
# Document and Vector Store Tests
# =============================================================================

@pytest.mark.asyncio
class TestDocumentOperations:
    """Test document upload and vector store operations.
    
    **Validates: Requirements 5.1**
    """

    @pytest.fixture
    def provider(self):
        """Create provider instance for testing."""
        return OpenAIProvider(api_key="sk-test-key")

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

    @pytest.mark.asyncio
    async def test_upload_document_raises_provider_error(self, provider, tmp_path):
        """Test that upload_document raises ProviderError on failure."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        with patch.object(provider.client.files, "create", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = openai.OpenAIError("Upload failed")
            
            with pytest.raises(ProviderError, match="Failed to upload document"):
                await provider.upload_document(str(test_file))

    @pytest.mark.asyncio
    async def test_create_vector_store(self, provider):
        """Test vector store creation (mocked)."""
        mock_vs = MagicMock()
        mock_vs.id = "vs_test123"
        mock_vs.name = "test-store"

        with patch.object(provider.client.vector_stores, "create", new_callable=AsyncMock) as mock_create:
            with patch.object(provider.client.vector_stores.files, "create", new_callable=AsyncMock) as mock_file_create:
                mock_create.return_value = mock_vs
                mock_file_create.return_value = None

                vs = await provider.create_vector_store("test-store", ["file_1", "file_2"])

                assert vs.id == "vs_test123"
                assert vs.name == "test-store"
                assert vs.file_ids == ["file_1", "file_2"]
                mock_create.assert_called_once_with(name="test-store")
                assert mock_file_create.call_count == 2

    @pytest.mark.asyncio
    async def test_create_vector_store_raises_provider_error(self, provider):
        """Test that create_vector_store raises ProviderError on failure."""
        with patch.object(provider.client.vector_stores, "create", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = openai.OpenAIError("Creation failed")
            
            with pytest.raises(ProviderError, match="Failed to create vector store"):
                await provider.create_vector_store("test-store", ["file_1"])

    @pytest.mark.asyncio
    async def test_delete_vector_store(self, provider):
        """Test vector store deletion (mocked)."""
        with patch.object(provider.client.vector_stores, "delete", new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = None

            success = await provider.delete_vector_store("vs_test123")

            assert success is True
            mock_delete.assert_called_once_with("vs_test123")

    @pytest.mark.asyncio
    async def test_delete_vector_store_raises_provider_error(self, provider):
        """Test that delete_vector_store raises ProviderError on failure."""
        with patch.object(provider.client.vector_stores, "delete", new_callable=AsyncMock) as mock_delete:
            mock_delete.side_effect = openai.OpenAIError("Delete failed")
            
            with pytest.raises(ProviderError, match="Failed to delete vector store"):
                await provider.delete_vector_store("vs_test123")

    @pytest.mark.asyncio
    async def test_list_vector_stores(self, provider):
        """Test listing vector stores (mocked)."""
        mock_vs1 = MagicMock()
        mock_vs1.id = "vs_1"
        mock_vs1.name = "store-1"
        
        mock_vs2 = MagicMock()
        mock_vs2.id = "vs_2"
        mock_vs2.name = "store-2"
        
        mock_file = MagicMock()
        mock_file.id = "file_1"
        
        mock_list_response = MagicMock()
        mock_list_response.data = [mock_vs1, mock_vs2]
        
        mock_files_response = MagicMock()
        mock_files_response.data = [mock_file]

        with patch.object(provider.client.vector_stores, "list", new_callable=AsyncMock) as mock_list:
            with patch.object(provider.client.vector_stores.files, "list", new_callable=AsyncMock) as mock_files_list:
                mock_list.return_value = mock_list_response
                mock_files_list.return_value = mock_files_response

                stores = await provider.list_vector_stores()

                assert len(stores) == 2
                assert stores[0].id == "vs_1"
                assert stores[0].name == "store-1"
                assert stores[1].id == "vs_2"

    @pytest.mark.asyncio
    async def test_list_vector_stores_raises_provider_error(self, provider):
        """Test that list_vector_stores raises ProviderError on failure."""
        with patch.object(provider.client.vector_stores, "list", new_callable=AsyncMock) as mock_list:
            mock_list.side_effect = openai.OpenAIError("List failed")
            
            with pytest.raises(ProviderError, match="Failed to list vector stores"):
                await provider.list_vector_stores()

    @pytest.mark.asyncio
    async def test_wait_for_vector_store_success(self, provider):
        """Test waiting for vector store ingestion (mocked)."""
        mock_file = MagicMock()
        mock_file.status = "completed"
        
        mock_listing = MagicMock()
        mock_listing.data = [mock_file]

        with patch.object(provider.client.vector_stores.files, "list", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = mock_listing

            success = await provider.wait_for_vector_store("vs_test123", timeout=10)

            assert success is True

    @pytest.mark.asyncio
    async def test_wait_for_vector_store_timeout(self, provider):
        """Test that wait_for_vector_store raises TimeoutError."""
        mock_file = MagicMock()
        mock_file.status = "in_progress"  # Never completes
        
        mock_listing = MagicMock()
        mock_listing.data = [mock_file]

        with patch.object(provider.client.vector_stores.files, "list", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = mock_listing

            with pytest.raises(TimeoutError, match="timeout"):
                await provider.wait_for_vector_store("vs_test123", timeout=0.1, poll_interval=0.05)


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
