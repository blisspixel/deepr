"""Unit tests for MCP provider - Resources, Prompts, Sampling.

Tests resource URI routing, prompt template existence and structure,
and sampling fallback when client doesn't support it.

Feature: mcp-client-agent-interop
Requirements: 9.1, 10.1, 11.3
"""

from __future__ import annotations

from typing import Any

import pytest

from deepr.mcp.provider.prompts import PromptRenderer
from deepr.mcp.provider.resources import ResourceHandler
from deepr.mcp.provider.sampling import SamplingHandler, SamplingRequest

# --- Mock implementations ---


class FakeExpertState:
    """Fake expert state for unit tests."""

    def __init__(self) -> None:
        self._experts: dict[str, dict[str, Any]] = {
            "analyst": {
                "knowledge": {
                    "claim_count": 42,
                    "average_confidence": 0.85,
                    "last_updated": "2024-01-15T10:00:00Z",
                },
                "gaps": [
                    {"description": "Market size", "category": "strategic", "priority": 8.0},
                    {"description": "DNS records", "category": "infrastructure", "priority": 3.0},
                    {"description": "Revenue data", "category": "strategic", "priority": 9.5},
                ],
            },
        }

    def get_expert_names(self) -> list[str]:
        return list(self._experts.keys())

    def get_knowledge(self, name: str) -> dict[str, Any]:
        return self._experts.get(name, {}).get("knowledge", {})

    def get_gaps(self, name: str) -> list[dict[str, Any]]:
        return self._experts.get(name, {}).get("gaps", [])


class FakeCostState:
    """Fake cost state for unit tests."""

    def get_daily_spend(self) -> float:
        return 2.50

    def get_monthly_spend(self) -> float:
        return 45.00

    def get_remaining_budget(self) -> float:
        return 55.00

    def get_active_job_count(self) -> int:
        return 3


class FakeSamplingClient:
    """Fake client that does NOT support sampling (returns None)."""

    async def create_message(self, prompt: str, max_tokens: int) -> dict[str, Any] | None:
        return None


class FakeFallbackProvider:
    """Fake fallback provider."""

    async def complete(self, prompt: str, max_tokens: int) -> str:
        return f"fallback:{prompt[:20]}"


class FakeTraceLog:
    """Fake trace log."""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def record(self, entry_type: str, data: dict[str, Any]) -> None:
        self.entries.append({"type": entry_type, "data": data})


# --- Resource URI routing tests ---


class TestResourceRouting:
    """Test resource URI routing."""

    def setup_method(self) -> None:
        self.handler = ResourceHandler(
            expert_state=FakeExpertState(),
            cost_state=FakeCostState(),
        )

    def test_experts_list_uri(self) -> None:
        """deepr://experts/list returns expert names."""
        result = self.handler.handle("deepr://experts/list")
        assert result is not None
        assert result.uri == "deepr://experts/list"
        assert "analyst" in result.content

    def test_expert_knowledge_uri(self) -> None:
        """deepr://experts/{name}/knowledge returns knowledge state."""
        result = self.handler.handle("deepr://experts/analyst/knowledge")
        assert result is not None
        assert result.uri == "deepr://experts/analyst/knowledge"
        assert result.content["claim_count"] == 42

    def test_expert_gaps_uri(self) -> None:
        """deepr://experts/{name}/gaps returns sorted gaps."""
        result = self.handler.handle("deepr://experts/analyst/gaps")
        assert result is not None
        assert result.uri == "deepr://experts/analyst/gaps"
        # Verify sorted descending by priority
        priorities = [g["priority"] for g in result.content]
        assert priorities == sorted(priorities, reverse=True)

    def test_costs_summary_uri(self) -> None:
        """deepr://costs/summary returns cost data."""
        result = self.handler.handle("deepr://costs/summary")
        assert result is not None
        assert result.content["daily_spend"] == 2.50
        assert result.content["monthly_spend"] == 45.00
        assert result.content["remaining_budget"] == 55.00
        assert result.content["active_job_count"] == 3

    def test_unknown_uri_returns_none(self) -> None:
        """Unknown URIs return None."""
        result = self.handler.handle("deepr://unknown/path")
        assert result is None

    def test_no_state_returns_empty(self) -> None:
        """Handler with no state returns empty results."""
        handler = ResourceHandler()
        result = handler.handle("deepr://experts/list")
        assert result is not None
        assert result.content == []


# --- Prompt template tests ---


class TestPromptTemplates:
    """Test prompt template existence and structure."""

    def setup_method(self) -> None:
        self.renderer = PromptRenderer()

    def test_research_workflow_exists(self) -> None:
        """research-workflow template is registered."""
        assert self.renderer.has_template("research-workflow")

    def test_expert_consult_exists(self) -> None:
        """expert-consult template is registered."""
        assert self.renderer.has_template("expert-consult")

    def test_sector_analysis_exists(self) -> None:
        """sector-analysis template is registered."""
        assert self.renderer.has_template("sector-analysis")

    def test_research_workflow_parameters(self) -> None:
        """research-workflow has expected parameters."""
        template = self.renderer.get_template("research-workflow")
        assert template is not None
        assert "topic" in template.parameters
        assert "budget" in template.parameters
        assert "expert" in template.parameters

    def test_expert_consult_parameters(self) -> None:
        """expert-consult has expected parameters."""
        template = self.renderer.get_template("expert-consult")
        assert template is not None
        assert "expert" in template.parameters
        assert "question" in template.parameters
        assert "context" in template.parameters

    def test_sector_analysis_parameters(self) -> None:
        """sector-analysis has expected parameters."""
        template = self.renderer.get_template("sector-analysis")
        assert template is not None
        assert "sector" in template.parameters
        assert "companies" in template.parameters

    def test_unknown_template_raises(self) -> None:
        """Rendering unknown template raises KeyError."""
        with pytest.raises(KeyError):
            self.renderer.render("nonexistent", {})

    def test_list_templates_returns_all(self) -> None:
        """list_templates returns all three built-in templates."""
        templates = self.renderer.list_templates()
        names = [t["name"] for t in templates]
        assert "research-workflow" in names
        assert "expert-consult" in names
        assert "sector-analysis" in names


# --- Sampling fallback tests ---


class TestSamplingFallback:
    """Test sampling fallback when client doesn't support it."""

    @pytest.mark.asyncio
    async def test_fallback_when_no_client(self) -> None:
        """Falls back to own provider when no client configured."""
        fallback = FakeFallbackProvider()
        trace_log = FakeTraceLog()
        handler = SamplingHandler(client=None, fallback=fallback, trace_log=trace_log)

        request = SamplingRequest(prompt="Analyze market trends")
        response = await handler.sample(request)

        assert response.used_fallback is True
        assert response.content.startswith("fallback:")

    @pytest.mark.asyncio
    async def test_fallback_when_client_returns_none(self) -> None:
        """Falls back when client returns None (doesn't support sampling)."""
        client = FakeSamplingClient()
        fallback = FakeFallbackProvider()
        trace_log = FakeTraceLog()
        handler = SamplingHandler(client=client, fallback=fallback, trace_log=trace_log)

        request = SamplingRequest(prompt="Synthesize findings")
        response = await handler.sample(request)

        assert response.used_fallback is True
        assert response.content.startswith("fallback:")

    @pytest.mark.asyncio
    async def test_trace_recorded_on_fallback(self) -> None:
        """Trace entry is recorded even when using fallback."""
        trace_log = FakeTraceLog()
        fallback = FakeFallbackProvider()
        handler = SamplingHandler(client=None, fallback=fallback, trace_log=trace_log)

        request = SamplingRequest(prompt="Test prompt")
        await handler.sample(request)

        assert len(trace_log.entries) == 1
        entry = trace_log.entries[0]
        assert entry["type"] == "sampling"
        assert entry["data"]["prompt_length"] == len("Test prompt")
        assert entry["data"]["used_fallback"] is True

    def test_max_tokens_in_request(self) -> None:
        """SamplingRequest includes maxTokens parameter."""
        request = SamplingRequest(prompt="Test", max_tokens=2048)
        assert request.max_tokens == 2048
