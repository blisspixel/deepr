"""Regression test: the OpenAI provider must NOT mutate the caller's
ResearchRequest when falling back to a cheaper model on rate-limit.

Before the fix, ``request.model`` was set in place; the caller (which
might be persisting the request as a decision record, or retrying
against a different provider) would observe the silent downgrade -
e.g. from o3-deep-research ($11/$44 per MTok) to o4-mini-deep-research
($1.10/$4.40 per MTok).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import openai
import pytest

from deepr.providers.base import ResearchRequest
from deepr.providers.openai_provider import OpenAIProvider


@pytest.mark.asyncio
async def test_rate_limit_fallback_does_not_mutate_request():
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

    # The fallback path will recursively call submit_research with the
    # cheaper model; mock so that returns successfully.
    fallback_resp = type("R", (), {"id": "fallback-job-id"})()

    call_history = []

    async def fake_create(**payload):
        call_history.append(payload.get("model"))
        if len(call_history) <= 3:
            raise rate_limit_err
        return fallback_resp

    with patch.object(provider.client.responses, "create", new=AsyncMock(side_effect=fake_create)):
        job_id = await provider.submit_research(request)

    # The caller's request object is unchanged. This is the core
    # invariant - the silent quality downgrade in the previous code
    # mutated request.model, so a caller persisting the request as a
    # decision record would see the wrong model.
    assert request.model == original_model, "submit_research mutated the caller's request.model on rate-limit fallback"
    # The fallback path actually ran.
    assert job_id == "fallback-job-id"
    # Multiple distinct models were attempted (original then fallback).
    assert len(set(call_history)) >= 2
