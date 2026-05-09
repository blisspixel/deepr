"""Property tests for MCP provider sampling.

Feature: mcp-client-agent-interop
Property: 23
Validates: Requirements 11.4
"""

from __future__ import annotations

import asyncio
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from deepr.mcp.provider.sampling import SamplingHandler, SamplingRequest

# --- Mock implementations ---

class MockSamplingClient:
    """Mock MCP client that supports sampling."""

    def __init__(self, response: str = "test response") -> None:
        self._response = response

    async def create_message(self, prompt: str, max_tokens: int) -> dict[str, Any]:
        return {"content": self._response, "model": "test-model"}


class MockFallbackProvider:
    """Mock fallback provider."""

    def __init__(self, response: str = "fallback response") -> None:
        self._response = response

    async def complete(self, prompt: str, max_tokens: int) -> str:
        return self._response


class MockTraceLog:
    """Mock trace log that records entries."""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def record(self, entry_type: str, data: dict[str, Any]) -> None:
        self.entries.append({"type": entry_type, "data": data})


# --- Strategies ---

prompt_st = st.text(min_size=1, max_size=200)
max_tokens_st = st.integers(min_value=1, max_value=4096)


# --- Property 23: Sampling trace logging ---

@settings(max_examples=100)
@given(
    prompt=prompt_st,
    max_tokens=max_tokens_st,
)
def test_sampling_trace_logging(prompt: str, max_tokens: int) -> None:
    """Property 23: Sampling trace logging.

    For any sampling request, the trace log entry contains
    prompt_length, response_length, and latency_ms fields with correct values.

    **Validates: Requirements 11.4**
    """
    trace_log = MockTraceLog()
    client = MockSamplingClient(response="generated text")
    handler = SamplingHandler(
        client=client,
        trace_log=trace_log,
    )

    request = SamplingRequest(prompt=prompt, max_tokens=max_tokens)
    asyncio.get_event_loop().run_until_complete(handler.sample(request))

    # Verify trace entry was recorded
    assert len(trace_log.entries) == 1
    entry = trace_log.entries[0]
    assert entry["type"] == "sampling"

    data = entry["data"]
    assert data["prompt_length"] == len(prompt)
    assert data["response_length"] == len("generated text")
    assert data["latency_ms"] >= 0


@settings(max_examples=100)
@given(prompt=prompt_st)
def test_sampling_fallback_trace_logging(prompt: str) -> None:
    """Sampling with fallback also records trace entries.

    **Validates: Requirements 11.4**
    """
    trace_log = MockTraceLog()
    fallback = MockFallbackProvider(response="fallback text")
    # No client → forces fallback
    handler = SamplingHandler(
        client=None,
        fallback=fallback,
        trace_log=trace_log,
    )

    request = SamplingRequest(prompt=prompt)
    response = asyncio.get_event_loop().run_until_complete(handler.sample(request))

    assert response.used_fallback is True
    assert len(trace_log.entries) == 1

    data = trace_log.entries[0]["data"]
    assert data["prompt_length"] == len(prompt)
    assert data["response_length"] == len("fallback text")
    assert data["used_fallback"] is True
