"""Sampling request and fallback logic for MCP provider.

Issues sampling/createMessage requests to connected MCP clients
with fallback to Deepr's own provider and trace logging.

Feature: mcp-client-agent-interop
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)


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
    """Handle sampling requests with fallback and trace logging.

    Issues sampling/createMessage requests to the connected MCP client.
    Falls back to Deepr's own provider if the client doesn't support
    sampling. Records all requests in the trace log.

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
        """Issue a sampling request with fallback.

        Tries the MCP client first. If not supported or unavailable,
        falls back to Deepr's own provider.
        """
        start = time.monotonic()
        used_fallback = False
        content = ""
        model = request.model

        # Try MCP client sampling
        if self._client is not None:
            try:
                result = await self._client.create_message(
                    request.prompt,
                    request.max_tokens,
                )
                if result is not None:
                    content = result.get("content", "")
                    model = result.get("model", model)
                else:
                    used_fallback = True
            except Exception:
                logger.debug("MCP sampling failed, using fallback")
                used_fallback = True
        else:
            used_fallback = True

        # Fallback to Deepr's provider
        if used_fallback and self._fallback is not None:
            content = await self._fallback.complete(
                request.prompt,
                request.max_tokens,
            )

        latency_ms = (time.monotonic() - start) * 1000

        # Record trace entry
        entry = SamplingTraceEntry(
            prompt_length=len(request.prompt),
            response_length=len(content),
            latency_ms=round(latency_ms, 1),
            model=model,
            used_fallback=used_fallback,
            timestamp=time.time(),
        )
        self._trace_entries.append(entry)

        if self._trace_log is not None:
            self._trace_log.record("sampling", {
                "prompt_length": entry.prompt_length,
                "response_length": entry.response_length,
                "latency_ms": entry.latency_ms,
                "model": entry.model,
                "used_fallback": entry.used_fallback,
            })

        return SamplingResponse(
            content=content,
            model=model,
            used_fallback=used_fallback,
        )

    @property
    def trace_entries(self) -> list[SamplingTraceEntry]:
        """Get all trace entries for sampling requests."""
        return list(self._trace_entries)
