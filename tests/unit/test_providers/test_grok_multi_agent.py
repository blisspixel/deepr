"""Tests for Grok 4.20 multi-agent research via client-side fan-out."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepr.providers.base import ResearchRequest


def _make_mock_response(content="Agent output", prompt_tokens=100, completion_tokens=200):
    """Create a mock chat completion response."""
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    usage.total_tokens = prompt_tokens + completion_tokens

    message = MagicMock()
    message.content = content

    choice = MagicMock()
    choice.message = message

    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    return response


@pytest.fixture
def mock_grok_provider():
    """Create a GrokProvider with mocked client."""
    with patch.dict("os.environ", {"XAI_API_KEY": "test-key"}):
        from deepr.providers.grok_provider import GrokProvider

        provider = GrokProvider(api_key="test-key")
        provider.client = AsyncMock()
        return provider


class TestDetermineAgentCount:
    def test_explicit_count(self, mock_grok_provider):
        request = ResearchRequest(
            prompt="test",
            model="grok-4.20-multi-agent",
            system_message="",
            agent_count=8,
        )
        assert mock_grok_provider._determine_agent_count(request) == 8

    def test_clamps_min_4(self, mock_grok_provider):
        request = ResearchRequest(
            prompt="test",
            model="grok-4.20-multi-agent",
            system_message="",
            agent_count=1,
        )
        assert mock_grok_provider._determine_agent_count(request) == 4

    def test_clamps_max_16(self, mock_grok_provider):
        request = ResearchRequest(
            prompt="test",
            model="grok-4.20-multi-agent",
            system_message="",
            agent_count=32,
        )
        assert mock_grok_provider._determine_agent_count(request) == 16

    def test_heuristic_short_prompt(self, mock_grok_provider):
        request = ResearchRequest(
            prompt="What is AI?",
            model="grok-4.20-multi-agent",
            system_message="",
        )
        count = mock_grok_provider._determine_agent_count(request)
        assert 4 <= count <= 6

    def test_heuristic_complex_prompt(self, mock_grok_provider):
        request = ResearchRequest(
            prompt=" ".join(["word"] * 120) + " compare the aspects? how? why? what are the differences?",
            model="grok-4.20-multi-agent",
            system_message="",
        )
        count = mock_grok_provider._determine_agent_count(request)
        assert count >= 8

    def test_budget_constraint(self, mock_grok_provider):
        request = ResearchRequest(
            prompt=" ".join(["word"] * 120) + " compare and contrast?",
            model="grok-4.20-multi-agent",
            system_message="",
            per_agent_budget=0.01,
        )
        count = mock_grok_provider._determine_agent_count(request)
        assert count == 4


class TestGenerateSubQueries:
    def test_generates_correct_count(self, mock_grok_provider):
        queries = mock_grok_provider._generate_sub_queries("test prompt", 6)
        assert len(queries) == 6

    def test_each_query_contains_original(self, mock_grok_provider):
        queries = mock_grok_provider._generate_sub_queries("my question", 4)
        for q in queries:
            assert "my question" in q

    def test_each_query_has_directive(self, mock_grok_provider):
        queries = mock_grok_provider._generate_sub_queries("test", 4)
        for q in queries:
            assert "[Research Directive:" in q

    def test_directives_differ(self, mock_grok_provider):
        queries = mock_grok_provider._generate_sub_queries("test", 4)
        directives = [q.split("[Research Directive:")[1] for q in queries]
        assert len(set(directives)) == 4  # All different


class TestMultiAgentExecution:
    @pytest.mark.asyncio
    async def test_multi_agent_model_routes_correctly(self, mock_grok_provider):
        """Multi-agent model should trigger _execute_multi_agent_research."""
        mock_grok_provider.client.chat.completions.create = AsyncMock(
            return_value=_make_mock_response("result")
        )

        request = ResearchRequest(
            prompt="Research AI safety",
            model="grok-4.20-multi-agent",
            system_message="",
            agent_count=4,
        )

        job_id = await mock_grok_provider.submit_research(request)
        job = mock_grok_provider.jobs[job_id]

        assert job["status"] == "completed"
        assert job.get("agent_count", 0) >= 1
        assert job.get("trace_id") is not None

    @pytest.mark.asyncio
    async def test_single_model_routes_normally(self, mock_grok_provider):
        """Non-multi-agent model should use normal execution."""
        mock_grok_provider.client.chat.completions.create = AsyncMock(
            return_value=_make_mock_response("single result")
        )

        request = ResearchRequest(
            prompt="Simple question",
            model="grok-4.20-0309-reasoning",
            system_message="",
        )

        job_id = await mock_grok_provider.submit_research(request)
        job = mock_grok_provider.jobs[job_id]

        assert job["status"] == "completed"
        assert "agent_count" not in job  # Single agent, no multi-agent metadata

    @pytest.mark.asyncio
    async def test_multi_agent_cost_aggregation(self, mock_grok_provider):
        """Total cost should be sum of all agent costs + synthesis."""
        mock_grok_provider.client.chat.completions.create = AsyncMock(
            return_value=_make_mock_response("result", prompt_tokens=100, completion_tokens=200)
        )

        request = ResearchRequest(
            prompt="Complex research",
            model="grok-4.20-multi-agent",
            system_message="",
            agent_count=4,
        )

        job_id = await mock_grok_provider.submit_research(request)
        job = mock_grok_provider.jobs[job_id]

        assert job["cost"] > 0
        # 4 agents + 1 synthesis = 5 API calls
        assert mock_grok_provider.client.chat.completions.create.call_count == 5

    @pytest.mark.asyncio
    async def test_multi_agent_fallback_on_partial_failure(self, mock_grok_provider):
        """Should still produce results even if some agents fail."""
        call_count = 0

        async def _mock_create(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("Agent 2 network error")
            return _make_mock_response(f"Result from call {call_count}")

        mock_grok_provider.client.chat.completions.create = _mock_create

        request = ResearchRequest(
            prompt="Research topic",
            model="grok-4.20-multi-agent",
            system_message="",
            agent_count=4,
        )

        job_id = await mock_grok_provider.submit_research(request)
        job = mock_grok_provider.jobs[job_id]

        # Should still complete (some agents succeeded + synthesis)
        assert job["status"] == "completed"
        # At least some agents should have results
        completed_agents = [r for r in job.get("agent_results", []) if r["status"] == "completed"]
        assert len(completed_agents) >= 3  # 3 out of 4 succeeded


class TestSynthesiseMultiAgent:
    @pytest.mark.asyncio
    async def test_synthesis_combines_outputs(self, mock_grok_provider):
        mock_grok_provider.client.chat.completions.create = AsyncMock(
            return_value=_make_mock_response("Unified synthesis")
        )

        result = await mock_grok_provider._synthesise_multi_agent(
            "test query",
            ["Output A", "Output B"],
            "grok-4.20-0309-reasoning",
        )

        assert result["content"] == "Unified synthesis"
        assert result["cost"] > 0

    @pytest.mark.asyncio
    async def test_synthesis_empty_outputs(self, mock_grok_provider):
        result = await mock_grok_provider._synthesise_multi_agent(
            "test query",
            [],
            "grok-4.20-0309-reasoning",
        )
        assert "No agent outputs" in result["content"]
        assert result["cost"] == 0.0

    @pytest.mark.asyncio
    async def test_synthesis_fallback_on_error(self, mock_grok_provider):
        mock_grok_provider.client.chat.completions.create = AsyncMock(
            side_effect=Exception("API error")
        )

        result = await mock_grok_provider._synthesise_multi_agent(
            "test query",
            ["Output A"],
            "grok-4.20-0309-reasoning",
        )

        assert "Synthesis failed" in result["content"]
        assert "Output A" in result["content"]  # Raw output included as fallback
