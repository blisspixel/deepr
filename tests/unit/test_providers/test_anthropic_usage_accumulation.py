"""Regression tests: Anthropic provider accumulates per-turn usage and
returns a real ResearchResponse from get_status.

Previously every Anthropic ``submit_research`` discarded ``response.usage``
across the multi-turn tool loop and ``get_status`` returned $0 cost with
no output for every job — making the provider invisible to the cost
ledger while still being billed by Anthropic.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

ANTHROPIC_AVAILABLE = True
try:
    from deepr.providers.anthropic_provider import ANTHROPIC_AVAILABLE  # type: ignore
except ImportError:  # pragma: no cover
    ANTHROPIC_AVAILABLE = False


@pytest.mark.skipif(not ANTHROPIC_AVAILABLE, reason="Anthropic SDK not installed")
class TestAnthropicUsageAccumulation:
    @pytest.fixture
    def provider(self):
        from deepr.providers.anthropic_provider import AnthropicProvider

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("deepr.providers.anthropic_provider.Anthropic"):
                with patch("deepr.providers.anthropic_provider.ToolRegistry"):
                    return AnthropicProvider()

    @pytest.mark.asyncio
    async def test_submits_and_stores_usage(self, provider):
        """A successful submit_research should accumulate usage and the
        stored ResearchResponse should have a non-zero cost."""
        from deepr.providers.base import ResearchRequest

        # Build a fake single-turn response: thinking + text, no tool use.
        text_block = SimpleNamespace(type="text", text="The answer is 42.")
        thinking_block = SimpleNamespace(type="thinking", thinking="reasoning...")
        fake_response = SimpleNamespace(
            content=[thinking_block, text_block],
            usage=SimpleNamespace(
                input_tokens=1000,
                output_tokens=500,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            ),
        )
        provider.client.messages = MagicMock()
        provider.client.messages.create = MagicMock(return_value=fake_response)

        req = ResearchRequest(prompt="What is the answer?", model="claude-opus-4-5", system_message="sys")

        job_id = await provider.submit_research(req)

        # Job is stored
        assert job_id in provider._jobs
        stored = provider._jobs[job_id]
        assert stored.status == "completed"
        # Usage was captured
        assert stored.usage is not None
        assert stored.usage.input_tokens == 1000
        assert stored.usage.output_tokens == 500
        # And a non-zero cost was computed (Opus is not free)
        assert (stored.usage.cost or 0) > 0
        # The report is present
        assert stored.output

    @pytest.mark.asyncio
    async def test_get_status_returns_stored_data(self, provider):
        """get_status round-trips the stored ResearchResponse."""
        from deepr.providers.base import ResearchResponse, UsageStats

        provider._jobs["my-job"] = ResearchResponse(
            id="my-job",
            status="completed",
            output=[{"type": "message", "content": [{"type": "text", "text": "hi"}]}],
            usage=UsageStats(input_tokens=10, output_tokens=20, cost=0.05),
        )
        response = await provider.get_status("my-job")
        assert response.status == "completed"
        assert response.usage is not None
        assert (response.usage.cost or 0) == 0.05
