"""Property-based tests for MCP client trace stitcher.

Feature: mcp-client-agent-interop
- Property 9: Trace ID injection and span completeness
- Property 10: Trace ID mismatch detection
"""

from __future__ import annotations

from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from deepr.mcp.client.base import MCPToolResult
from deepr.mcp.client.trace_stitcher import TraceStitcher

# --- Test doubles ---


class FakeMetadataEmitter:
    """Fake metadata emitter that records events."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def emit(self, event_type: str, data: dict[str, Any]) -> None:
        self.events.append((event_type, data))


# --- Strategies ---

trace_ids = st.from_regex(r"[a-f0-9]{16,32}", fullmatch=True)
server_names = st.from_regex(r"[a-z][a-z0-9\-]{0,15}", fullmatch=True)
tool_names = st.from_regex(r"[a-z_]{1,15}", fullmatch=True)
costs = st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False)

# Strategy for argument dicts (simple string keys/values)
argument_keys = st.from_regex(r"[a-z_]{1,10}", fullmatch=True)
argument_values = st.text(min_size=0, max_size=50)
arguments_strategy = st.dictionaries(
    keys=argument_keys.filter(lambda k: k not in ("trace_id", "span_id")),
    values=argument_values,
    max_size=5,
)


# Feature: mcp-client-agent-interop, Property 9: Trace ID injection and span completeness


@settings(max_examples=100)
@given(
    trace_id=trace_ids,
    server_name=server_names,
    tool_name=tool_names,
    arguments=arguments_strategy,
    cost=costs,
    has_error=st.booleans(),
)
def test_property_9_trace_injection_and_span_completeness(
    trace_id: str,
    server_name: str,
    tool_name: str,
    arguments: dict[str, str],
    cost: float,
    has_error: bool,
) -> None:
    """For any set of external tool calls, the TraceStitcher SHALL: inject the parent
    trace_id into each call's arguments, assign a unique span_id to each call, and
    each completed span SHALL contain server_name, tool_name, latency_ms, and cost fields.

    **Validates: Requirements 4.1, 4.3, 4.4**
    """
    emitter = FakeMetadataEmitter()
    stitcher = TraceStitcher(metadata_emitter=emitter)

    # Create span
    span = stitcher.create_span(trace_id, server_name, tool_name)

    # Verify span has correct fields
    assert span.trace_id == trace_id
    assert span.server_name == server_name
    assert span.tool_name == tool_name
    assert len(span.span_id) == 16  # hex UUID prefix

    # Inject trace into arguments
    injected = stitcher.inject_trace(arguments, span.trace_id, span.span_id)

    # Verify injection
    assert injected["trace_id"] == trace_id
    assert injected["span_id"] == span.span_id
    # Original arguments preserved
    for key, value in arguments.items():
        assert injected[key] == value
    # Original dict not mutated
    assert "trace_id" not in arguments or arguments.get("trace_id") != trace_id

    # Complete span
    result = MCPToolResult(
        content="" if has_error else "result data",
        error="test error" if has_error else "",
        server_name=server_name,
        tool_name=tool_name,
        trace_id=trace_id,
    )
    stitcher.complete_span(span, result, cost)

    # Verify emitted event
    assert len(emitter.events) == 1
    event_type, event_data = emitter.events[0]
    assert event_type == "span_complete"
    assert event_data["trace_id"] == trace_id
    assert event_data["span_id"] == span.span_id
    assert event_data["server_name"] == server_name
    assert event_data["tool_name"] == tool_name
    assert "latency_ms" in event_data
    assert event_data["cost"] == cost
    assert event_data["status"] in ("ok", "error")


@settings(max_examples=100)
@given(
    trace_id=trace_ids,
    server_name=server_names,
    tool_name=tool_names,
    num_calls=st.integers(min_value=2, max_value=5),
)
def test_property_9_unique_span_ids(
    trace_id: str,
    server_name: str,
    tool_name: str,
    num_calls: int,
) -> None:
    """When multiple external tools are called in parallel, the TraceStitcher SHALL
    assign unique span IDs to each call while preserving the shared parent trace_id.

    **Validates: Requirements 4.4**
    """
    emitter = FakeMetadataEmitter()
    stitcher = TraceStitcher(metadata_emitter=emitter)

    spans = [stitcher.create_span(trace_id, server_name, f"{tool_name}_{i}") for i in range(num_calls)]

    # All spans share the same trace_id
    for span in spans:
        assert span.trace_id == trace_id

    # All span_ids are unique
    span_ids = [span.span_id for span in spans]
    assert len(set(span_ids)) == num_calls


# Feature: mcp-client-agent-interop, Property 10: Trace ID mismatch detection


@settings(max_examples=100)
@given(
    sent_trace_id=trace_ids,
    returned_trace_id=trace_ids,
)
def test_property_10_trace_id_mismatch_detection(
    sent_trace_id: str,
    returned_trace_id: str,
) -> None:
    """For any pair of (sent_trace_id, returned_trace_id), the TraceStitcher SHALL
    detect a mismatch if and only if sent_trace_id != returned_trace_id.

    **Validates: Requirements 4.2**
    """
    emitter = FakeMetadataEmitter()
    stitcher = TraceStitcher(metadata_emitter=emitter)

    is_mismatch = stitcher.check_trace_mismatch(sent_trace_id, returned_trace_id)

    expected_mismatch = sent_trace_id != returned_trace_id
    assert is_mismatch == expected_mismatch
