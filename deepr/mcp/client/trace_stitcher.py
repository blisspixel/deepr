"""Trace stitching for outbound MCP tool calls.

Creates child spans for external tool calls, injects trace context into
arguments, and records span completion with latency and cost.

Feature: mcp-client-agent-interop
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from deepr.mcp.client.base import MCPToolResult

logger = logging.getLogger(__name__)


@dataclass
class SpanContext:
    """Context for an in-flight trace span."""

    trace_id: str
    span_id: str
    server_name: str
    tool_name: str
    start_time: float
    metadata: dict[str, Any] = field(default_factory=dict)


class MetadataEmitterProtocol(Protocol):
    """Protocol for emitting structured observability events."""

    def emit(self, event_type: str, data: dict[str, Any]) -> None:
        """Emit a structured event."""
        ...


class TraceStitcher:
    """Create and manage trace spans for outbound MCP tool calls.

    Injects trace context into tool call arguments and records span
    completion with latency, cost, and status information.

    Usage::

        stitcher = TraceStitcher(metadata_emitter=my_emitter)
        span = stitcher.create_span("trace-123", "recon", "domain_lookup")
        args = stitcher.inject_trace({"domain": "example.com"}, span.trace_id, span.span_id)
        # ... dispatch tool call ...
        stitcher.complete_span(span, result, cost=0.0)
    """

    def __init__(self, metadata_emitter: MetadataEmitterProtocol) -> None:
        self._emitter = metadata_emitter

    def create_span(
        self,
        trace_id: str,
        server_name: str,
        tool_name: str,
    ) -> SpanContext:
        """Create a child span for an outbound tool call.

        Assigns a unique span_id and records the start time.
        """
        span_id = uuid.uuid4().hex[:16]
        return SpanContext(
            trace_id=trace_id,
            span_id=span_id,
            server_name=server_name,
            tool_name=tool_name,
            start_time=time.monotonic(),
        )

    def inject_trace(
        self,
        arguments: dict[str, Any],
        trace_id: str,
        span_id: str,
    ) -> dict[str, Any]:
        """Inject trace context into tool call arguments.

        Returns a new dict with trace_id and span_id added.
        Does not mutate the original arguments dict.
        """
        result = dict(arguments)
        result["trace_id"] = trace_id
        result["span_id"] = span_id
        return result

    def complete_span(
        self,
        span: SpanContext,
        result: MCPToolResult,
        cost: float,
    ) -> None:
        """Complete a span with latency, cost, and status.

        Validates that the returned trace_id matches the sent trace_id
        and logs a warning on mismatch. Emits a structured event via
        the metadata emitter.
        """
        latency_ms = (time.monotonic() - span.start_time) * 1000
        status = "ok" if result.ok else "error"

        # Validate trace_id if present in result
        returned_trace_id = result.trace_id
        if returned_trace_id and returned_trace_id != span.trace_id:
            logger.warning(
                "Trace ID mismatch for %s/%s: sent=%s, returned=%s",
                span.server_name,
                span.tool_name,
                span.trace_id,
                returned_trace_id,
            )

        event_data = {
            "trace_id": span.trace_id,
            "span_id": span.span_id,
            "server_name": span.server_name,
            "tool_name": span.tool_name,
            "latency_ms": round(latency_ms, 1),
            "cost": cost,
            "status": status,
        }

        self._emitter.emit("span_complete", event_data)

        logger.debug(
            "Span complete: %s/%s latency=%.1fms cost=%.4f status=%s",
            span.server_name,
            span.tool_name,
            latency_ms,
            cost,
            status,
        )

    def check_trace_mismatch(
        self,
        sent_trace_id: str,
        returned_trace_id: str,
    ) -> bool:
        """Check if there is a trace ID mismatch.

        Returns True if there IS a mismatch (sent != returned).
        """
        return sent_trace_id != returned_trace_id
