"""Fail-closed sampling request contracts for MCP provider.

Host sampling and provider fallback are both blocked until the exact capacity
behind a host request has enforceable zero-dollar or durable paid authority.

Feature: mcp-client-agent-interop
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class SamplingFallbackDisabledError(RuntimeError):
    """A sampling request cannot use host or fallback capacity without authority."""


@dataclass
class SamplingRequest:
    """A sampling request to be sent to the host."""

    prompt: str
    max_tokens: int = 1024
    model: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SamplingResponse:
    """Response from a sampling request."""

    content: str
    model: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    used_fallback: bool = False


@dataclass
class SamplingTraceEntry:
    """Trace log entry for a sampling request."""

    prompt_length: int
    response_length: int
    latency_ms: float
    model: str = ""
    used_fallback: bool = False
    timestamp: float = 0.0


class SamplingClientProtocol(Protocol):
    """Protocol for issuing sampling requests to the host."""

    async def create_message(
        self,
        prompt: str,
        max_tokens: int,
    ) -> dict[str, Any] | None:
        """Issue a sampling/createMessage request.

        Returns response dict or None if not supported.
        """
        ...


class FallbackProviderProtocol(Protocol):
    """Protocol for Deepr's own LLM provider as fallback."""

    async def complete(self, prompt: str, max_tokens: int) -> str:
        """Generate a completion using Deepr's provider."""
        ...


class TraceLogProtocol(Protocol):
    """Protocol for recording trace entries."""

    def record(self, entry_type: str, data: dict[str, Any]) -> None:
        """Record a trace entry."""
        ...


class SamplingHandler:
    """Retain the sampling API while refusing unproven host capacity.

    Both the connected host and a configured fallback may use metered capacity.
    Neither is dispatched because this compatibility surface has no trusted
    zero-dollar proof or durable cost transaction.

    Usage::

        handler = SamplingHandler(
            client=mcp_client,
            fallback=deepr_provider,
            trace_log=trace_log,
        )
        response = await handler.sample(SamplingRequest(prompt="Analyze..."))
    """

    def __init__(
        self,
        client: SamplingClientProtocol | None = None,
        fallback: FallbackProviderProtocol | None = None,
        trace_log: TraceLogProtocol | None = None,
    ) -> None:
        self._client = client
        self._fallback = fallback
        self._trace_log = trace_log
        self._trace_entries: list[SamplingTraceEntry] = []

    async def sample(self, request: SamplingRequest) -> SamplingResponse:
        """Refuse before invoking the MCP host or configured fallback."""
        del request
        raise SamplingFallbackDisabledError(
            "MCP host sampling and provider fallback are disabled until exact capacity has a trusted zero-dollar proof "
            "or durable reservation and settlement"
        )

    @property
    def trace_entries(self) -> list[SamplingTraceEntry]:
        """Get all trace entries for sampling requests."""
        return list(self._trace_entries)
