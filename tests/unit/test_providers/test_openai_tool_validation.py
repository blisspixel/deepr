"""Tests for OpenAI provider tool configuration validation.

These tests ensure that tools are correctly formatted according to OpenAI's
Responses API specification, catching parameter mismatches before they hit production.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepr.providers import OpenAIProvider
from deepr.providers.base import ResearchRequest, ToolConfig


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

            await provider.submit_research(request)

            # Verify the API was called with correct tool format
            call_kwargs = mock_create.call_args.kwargs
            tools = call_kwargs["tools"]

            assert len(tools) == 1
            assert tools[0]["type"] == "web_search_preview"
            assert "container" not in tools[0], "web_search_preview should NOT have container parameter"

    @pytest.mark.asyncio
    async def test_code_interpreter_requires_container(self, provider):
        """Test code_interpreter tool REQUIRES container parameter.

        Per OpenAI Responses API docs (lines 44-46 in documentation openai deep research.txt):
        code_interpreter requires {"type": "code_interpreter", "container": {"type": "auto"}}
        """
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

            await provider.submit_research(request)

            # Verify the API was called with correct tool format
            call_kwargs = mock_create.call_args.kwargs
            tools = call_kwargs["tools"]

            assert len(tools) == 1
            assert tools[0]["type"] == "code_interpreter"
            assert "container" in tools[0], "code_interpreter MUST have container parameter"
            assert tools[0]["container"] == {"type": "auto"}

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

            await provider.submit_research(request)

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
                    ToolConfig(type="code_interpreter"),
                    ToolConfig(type="file_search", vector_store_ids=["vs_123"]),
                ],
            )

            await provider.submit_research(request)

            # Verify the API was called with correct tool formats
            call_kwargs = mock_create.call_args.kwargs
            tools = call_kwargs["tools"]

            assert len(tools) == 3

            # web_search_preview: NO container
            assert tools[0]["type"] == "web_search_preview"
            assert "container" not in tools[0]

            # code_interpreter: REQUIRES container
            assert tools[1]["type"] == "code_interpreter"
            assert "container" in tools[1]
            assert tools[1]["container"] == {"type": "auto"}

            # file_search: REQUIRES vector_store_ids
            assert tools[2]["type"] == "file_search"
            assert "vector_store_ids" in tools[2]
            assert tools[2]["vector_store_ids"] == ["vs_123"]

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

            await provider.submit_research(request)

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

            await provider.submit_research(request)

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
                    ToolConfig(type="code_interpreter"),  # tools[2]
                ],
            )

            await provider.submit_research(request)

            call_kwargs = mock_create.call_args.kwargs
            tools = call_kwargs["tools"]

            # The bug was adding container to web_search_preview
            web_search = next(t for t in tools if t["type"] == "web_search_preview")
            assert "container" not in web_search, "REGRESSION: web_search_preview should NOT have container parameter"

            # But code_interpreter still needs it
            code_interp = next(t for t in tools if t["type"] == "code_interpreter")
            assert "container" in code_interp, "code_interpreter MUST have container parameter"
