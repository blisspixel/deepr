"""Tests for context builder service."""

from unittest.mock import MagicMock, patch

import pytest

from tests.unit.test_services.conftest import make_chat_response


class TestContextBuilder:
    """Test ContextBuilder context generation."""

    @pytest.fixture
    def mock_client(self):
        return MagicMock()

    @pytest.fixture
    def builder(self, mock_client, mock_openai_env):
        with patch("deepr.services.context_builder.OpenAI", return_value=mock_client):
            from deepr.services.context_builder import ContextBuilder

            return ContextBuilder()

    def test_init_with_explicit_key(self):
        """api_key passed directly to OpenAI."""
        with patch("deepr.services.context_builder.OpenAI") as mock_cls:
            from deepr.services.context_builder import ContextBuilder

            ContextBuilder(api_key="explicit-key")
            mock_cls.assert_called_once_with(api_key="explicit-key")

    def test_init_with_env_key(self, mock_openai_env):
        """Falls back to OPENAI_API_KEY env var."""
        with patch("deepr.services.context_builder.OpenAI") as mock_cls:
            from deepr.services.context_builder import ContextBuilder

            ContextBuilder()
            call_kwargs = mock_cls.call_args
            assert call_kwargs[1]["api_key"] == "sk-test-key-not-real"

    @pytest.mark.asyncio
    async def test_summarize_calls_llm(self, builder, mock_client):
        """summarize_research calls chat.completions.create."""
        mock_client.chat.completions.create.return_value = make_chat_response("- Key finding 1")
        await builder.summarize_research("Full report text here")
        mock_client.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_summarize_truncates_input(self, builder, mock_client):
        """Report content is truncated to first 20000 chars."""
        mock_client.chat.completions.create.return_value = make_chat_response("Summary")
        long_report = "x" * 30000
        await builder.summarize_research(long_report)
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        prompt = call_kwargs["messages"][0]["content"]
        # The report is sliced to [:20000]
        assert "x" * 20000 in prompt
        assert "x" * 30000 not in prompt

    @pytest.mark.asyncio
    async def test_summarize_returns_stripped_string(self, builder, mock_client):
        """Return value is a stripped string."""
        mock_client.chat.completions.create.return_value = make_chat_response("  Summary text  ")
        result = await builder.summarize_research("report")
        assert result == "Summary text"

    @pytest.mark.asyncio
    async def test_summarize_respects_max_tokens(self, builder, mock_client):
        """max_tokens parameter affects prompt target words."""
        mock_client.chat.completions.create.return_value = make_chat_response("Summary")
        await builder.summarize_research("report", max_tokens=200)
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["max_completion_tokens"] == 300  # 200 + 100 buffer

    @pytest.mark.asyncio
    async def test_build_phase_context_no_deps(self, builder):
        """Empty depends_on returns empty string."""
        task = {"prompt": "Do something", "depends_on": []}
        result = await builder.build_phase_context(task, {})
        assert result == ""

    @pytest.mark.asyncio
    async def test_build_phase_context_no_depends_key(self, builder):
        """Missing depends_on key returns empty string."""
        task = {"prompt": "Do something"}
        result = await builder.build_phase_context(task, {})
        assert result == ""

    @pytest.mark.asyncio
    async def test_build_phase_context_single_dep(self, builder, mock_client):
        """Single dependency is summarized and included."""
        mock_client.chat.completions.create.return_value = make_chat_response("Dep summary")
        task = {"prompt": "Analyze", "depends_on": [1]}
        completed = {1: {"title": "Background", "result": "Some findings"}}
        result = await builder.build_phase_context(task, completed)
        assert "Background" in result
        assert "Dep summary" in result

    @pytest.mark.asyncio
    async def test_build_phase_context_missing_dep_skipped(self, builder, mock_client):
        """Dependency not in completed_tasks is skipped."""
        mock_client.chat.completions.create.return_value = make_chat_response("Summary")
        task = {"prompt": "Analyze", "depends_on": [1, 99]}
        completed = {1: {"title": "First", "result": "Data"}}
        result = await builder.build_phase_context(task, completed)
        assert "First" in result
        # Should not crash on missing dep 99

    @pytest.mark.asyncio
    async def test_build_phase_context_empty_result_skipped(self, builder, mock_client):
        """Dependency with empty result is skipped."""
        task = {"prompt": "Analyze", "depends_on": [1]}
        completed = {1: {"title": "Empty", "result": ""}}
        result = await builder.build_phase_context(task, completed)
        # summarize_research should NOT be called for empty result
        mock_client.chat.completions.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_build_synthesis_context_all_tasks(self, builder, mock_client):
        """All tasks are summarized in order."""
        mock_client.chat.completions.create.return_value = make_chat_response("Task summary")
        tasks = {
            1: {"title": "First", "result": "Data 1"},
            2: {"title": "Second", "result": "Data 2"},
        }
        result = await builder.build_synthesis_context(tasks)
        assert "Research 1: First" in result
        assert "Research 2: Second" in result
        assert mock_client.chat.completions.create.call_count == 2

    @pytest.mark.asyncio
    async def test_build_synthesis_context_empty_tasks(self, builder, mock_client):
        """No tasks with results returns minimal context."""
        result = await builder.build_synthesis_context({})
        assert "comprehensive synthesis" in result
        mock_client.chat.completions.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_build_synthesis_context_skips_empty(self, builder, mock_client):
        """Tasks with empty results are skipped."""
        mock_client.chat.completions.create.return_value = make_chat_response("Summary")
        tasks = {
            1: {"title": "Has data", "result": "Content"},
            2: {"title": "Empty", "result": ""},
        }
        result = await builder.build_synthesis_context(tasks)
        assert "Has data" in result
        assert "Empty" not in result
        mock_client.chat.completions.create.assert_called_once()
