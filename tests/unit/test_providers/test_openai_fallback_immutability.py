"""A reserved OpenAI request never silently changes its priced model."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import openai
import pytest

from deepr.providers.base import ProviderError, ResearchRequest
from deepr.providers.openai_provider import OpenAIProvider


@pytest.mark.asyncio
async def test_rate_limit_never_falls_back_outside_reserved_model():
    request = ResearchRequest(
        prompt="test",
        model="o3-deep-research",
        system_message="sys",
        background=True,
    )
    original_model = request.model

    provider = OpenAIProvider(api_key="test-key")

    # First call raises RateLimitError on every attempt.
    rate_limit_err = openai.RateLimitError(
        message="rate limited",
        response=type("R", (), {"status_code": 429, "headers": {}, "request": None})(),
        body=None,
    )

    call_history = []

    async def fake_create(**payload):
        call_history.append(payload.get("model"))
        raise rate_limit_err

    with patch.object(provider.client.responses, "create", new=AsyncMock(side_effect=fake_create)):
        with pytest.raises(ProviderError, match="Failed after 3 retries"):
            await provider.submit_research(request)

    # The caller's request object is unchanged. This is the core
    # invariant - the silent quality downgrade in the previous code
    # mutated request.model, so a caller persisting the request as a
    # decision record would see the wrong model.
    assert request.model == original_model, "submit_research mutated the caller's request.model on rate-limit fallback"
    assert call_history == ["o3-deep-research-2025-06-26"] * 3
