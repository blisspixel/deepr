"""Tests for OpenAI provider tool configuration validation.

These tests ensure that tools are correctly formatted according to OpenAI's
Responses API specification, catching parameter mismatches before they hit production.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepr.providers import OpenAIProvider
from deepr.providers.base import ResearchRequest, ToolConfig
from deepr.providers.dispatch_authority import PaidDispatchAuthorityError
from tests.unit.test_providers._provider_authority import submit_adapter


@pytest.mark.asyncio
class TestOpenAIToolConfiguration:
    """Test OpenAI provider tool configuration."""

    @pytest.fixture
    def provider(self):
        """Create provider instance for testing."""
        return OpenAIProvider(api_key="sk-test-key")

    @pytest.mark.asyncio
    async def test_web_search_preview_no_container(self, provider):
        """Test web_search_preview tool does NOT include container parameter.

        Per OpenAI Responses API docs (line 36 in documentation openai deep research.txt):
        web_search_preview only requires {"type": "web_search_preview"}
        """
        mock_response = MagicMock()
        mock_response.id = "resp_test123"

        with patch.object(provider.client.responses, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response

            request = ResearchRequest(
                prompt="Test prompt",
                model="o4-mini-deep-research",
                system_message="Test system message",
                tools=[ToolConfig(type="web_search_preview")],
            )

            await submit_adapter(provider, request)

            # Verify the API was called with correct tool format
            call_kwargs = mock_create.call_args.kwargs
            tools = call_kwargs["tools"]

            assert len(tools) == 1
            assert tools[0]["type"] == "web_search_preview"
            assert "container" not in tools[0], "web_search_preview should NOT have container parameter"

    @pytest.mark.asyncio
    async def test_code_interpreter_requires_container(self, provider):
        """Code interpreter is blocked until its session charge is bounded."""
        mock_response = MagicMock()
        mock_response.id = "resp_test123"

        with patch.object(provider.client.responses, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response

            request = ResearchRequest(
                prompt="Test prompt",
                model="o4-mini-deep-research",
                system_message="Test system message",
                tools=[ToolConfig(type="code_interpreter")],
            )

            with pytest.raises(PaidDispatchAuthorityError, match="code_interpreter"):
                await submit_adapter(provider, request)
            mock_create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_file_search_with_vector_stores(self, provider):
        """Test file_search tool with vector_store_ids parameter.

        Per OpenAI Responses API docs (lines 38-43 in documentation openai deep research.txt):
        file_search requires vector_store_ids when used
        """
        mock_response = MagicMock()
        mock_response.id = "resp_test123"

        with patch.object(provider.client.responses, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response

            request = ResearchRequest(
                prompt="Test prompt",
                model="o4-mini-deep-research",
                system_message="Test system message",
                tools=[ToolConfig(type="file_search", vector_store_ids=["vs_123", "vs_456"])],
            )

            await submit_adapter(provider, request)

            # Verify the API was called with correct tool format
            call_kwargs = mock_create.call_args.kwargs
            tools = call_kwargs["tools"]

            assert len(tools) == 1
            assert tools[0]["type"] == "file_search"
            assert "vector_store_ids" in tools[0]
            assert tools[0]["vector_store_ids"] == ["vs_123", "vs_456"]

    @pytest.mark.asyncio
    async def test_multiple_tools_correct_format(self, provider):
        """Test multiple tools are formatted correctly together.

        This is the real-world scenario that failed 4 times before we fixed it.
        Each tool type has different parameter requirements.
        """
        mock_response = MagicMock()
        mock_response.id = "resp_test123"

        with patch.object(provider.client.responses, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response

            request = ResearchRequest(
                prompt="Test prompt",
                model="o4-mini-deep-research",
                system_message="Test system message",
                tools=[
                    ToolConfig(type="web_search_preview"),
                    ToolConfig(type="file_search", vector_store_ids=["vs_123"]),
                ],
            )

            await submit_adapter(provider, request)

            # Verify the API was called with correct tool formats
            call_kwargs = mock_create.call_args.kwargs
            tools = call_kwargs["tools"]

            assert len(tools) == 2

            # web_search_preview: NO container
            assert tools[0]["type"] == "web_search_preview"
            assert "container" not in tools[0]

            # file_search: REQUIRES vector_store_ids
            assert tools[1]["type"] == "file_search"
            assert "vector_store_ids" in tools[1]
            assert tools[1]["vector_store_ids"] == ["vs_123"]

    @pytest.mark.asyncio
    async def test_deep_research_requires_at_least_one_tool(self, provider):
        """Test that deep research models require at least one tool.

        Per OpenAI docs: "You must include at least one data source: web search,
        remote MCP servers, or file search with vector stores."

        This test documents the requirement but doesn't enforce it yet.
        """
        mock_response = MagicMock()
        mock_response.id = "resp_test123"

        with patch.object(provider.client.responses, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response

            # Deep research model with NO tools - should ideally validate this
            request = ResearchRequest(
                prompt="Test prompt",
                model="o4-mini-deep-research",
                system_message="Test system message",
                tools=[],  # Empty tools list
            )

            await submit_adapter(provider, request)

            # Current behavior: passes None when tools list is empty
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["tools"] is None

    @pytest.mark.asyncio
    async def test_file_search_without_vector_stores(self, provider):
        """Test file_search without vector_store_ids.

        This should probably be validated and prevented.
        """
        mock_response = MagicMock()
        mock_response.id = "resp_test123"

        with patch.object(provider.client.responses, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response

            request = ResearchRequest(
                prompt="Test prompt",
                model="o4-mini-deep-research",
                system_message="Test system message",
                tools=[ToolConfig(type="file_search", vector_store_ids=None)],
            )

            await submit_adapter(provider, request)

            # Current behavior: file_search without vector_store_ids
            call_kwargs = mock_create.call_args.kwargs
            tools = call_kwargs["tools"]

            assert len(tools) == 1
            assert tools[0]["type"] == "file_search"
            # This might cause API errors - consider validation


class TestToolParameterRegressions:
    """Regression tests for specific bugs we've encountered."""

    @pytest.mark.asyncio
    async def test_regression_container_on_web_search(self):
        """Regression test: web_search_preview should NOT have container parameter.

        Bug history:
        - Attempt 1: Unknown parameter 'tools[0].container' error
        - Attempt 2: Missing required parameter 'tools[1].container' error
        - Attempt 3: Unknown parameter 'tools[0].container' error again
        - Fix: Only code_interpreter needs container, not web_search_preview

        This test catches that specific mistake.
        """
        provider = OpenAIProvider(api_key="sk-test-key")
        mock_response = MagicMock()
        mock_response.id = "resp_test123"

        with patch.object(provider.client.responses, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response

            request = ResearchRequest(
                prompt="Test with file upload",
                model="o4-mini-deep-research",
                system_message="Test",
                tools=[
                    ToolConfig(type="file_search", vector_store_ids=["vs_123"]),  # tools[0]
                    ToolConfig(type="web_search_preview"),  # tools[1]
                ],
            )

            await submit_adapter(provider, request)

            call_kwargs = mock_create.call_args.kwargs
            tools = call_kwargs["tools"]

            # The bug was adding container to web_search_preview
            web_search = next(t for t in tools if t["type"] == "web_search_preview")
            assert "container" not in web_search, "REGRESSION: web_search_preview should NOT have container parameter"
