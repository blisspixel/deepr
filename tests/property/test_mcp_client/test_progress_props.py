"""Property-based tests for MCP client progress notifier.

Feature: mcp-client-agent-interop
- Property 13: Progress event structure
"""

from __future__ import annotations

from datetime import UTC, datetime

from hypothesis import given, settings
from hypothesis import strategies as st

from deepr.mcp.client.progress_notifier import ProgressEvent, ProgressNotifier

# --- Strategies ---

server_names = st.from_regex(r"[a-z][a-z0-9\-]{0,15}", fullmatch=True)
tool_names = st.from_regex(r"[a-z_]{1,15}", fullmatch=True)
phases = st.from_regex(r"[a-z][a-z_ ]{0,20}", fullmatch=True)
progress_pcts = st.one_of(
    st.none(),
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
)
elapsed_seconds = st.floats(min_value=0.01, max_value=3600.0, allow_nan=False, allow_infinity=False)


# Feature: mcp-client-agent-interop, Property 13: Progress event structure


@settings(max_examples=100)
@given(
    server_name=server_names,
    tool_name=tool_names,
    progress_pct=progress_pcts,
    phase=phases,
    elapsed=elapsed_seconds,
)
def test_property_13_progress_event_structure(
    server_name: str,
    tool_name: str,
    progress_pct: float | None,
    phase: str,
    elapsed: float,
) -> None:
    """For any raw MCP progress notification, the emitted ProgressEvent SHALL contain:
    server_name, tool_name, progress_pct (or None), phase description, and
    elapsed_seconds > 0.

    **Validates: Requirements 6.4**
    """
    notifier = ProgressNotifier()
    received_events: list[ProgressEvent] = []

    def callback(event: ProgressEvent) -> None:
        received_events.append(event)

    # Subscribe
    sub_id = notifier.subscribe(server_name, callback)
    assert sub_id  # Non-empty subscription ID

    # Create and emit event
    event = ProgressEvent(
        server_name=server_name,
        tool_name=tool_name,
        progress_pct=progress_pct,
        phase=phase,
        elapsed_seconds=elapsed,
        timestamp=datetime.now(UTC),
    )
    notifier.emit(event)

    # Verify delivery
    assert len(received_events) == 1
    received = received_events[0]

    # Verify structure
    assert received.server_name == server_name
    assert received.tool_name == tool_name
    assert received.progress_pct == progress_pct
    assert received.phase == phase
    assert received.elapsed_seconds > 0
    assert isinstance(received.timestamp, datetime)

    # Cleanup
    notifier.unsubscribe(sub_id)


@settings(max_examples=100)
@given(
    server_name=server_names,
    other_server=server_names,
    tool_name=tool_names,
    phase=phases,
    elapsed=elapsed_seconds,
)
def test_property_13_emit_dispatches_to_correct_server(
    server_name: str,
    other_server: str,
    tool_name: str,
    phase: str,
    elapsed: float,
) -> None:
    """Emit dispatches events only to subscribers for the matching server_name.

    **Validates: Requirements 6.4**
    """
    notifier = ProgressNotifier()
    target_events: list[ProgressEvent] = []
    other_events: list[ProgressEvent] = []

    sub1 = notifier.subscribe(server_name, target_events.append)
    sub2 = notifier.subscribe(other_server, other_events.append)

    event = ProgressEvent(
        server_name=server_name,
        tool_name=tool_name,
        progress_pct=None,
        phase=phase,
        elapsed_seconds=elapsed,
        timestamp=datetime.now(UTC),
    )
    notifier.emit(event)

    # Target server subscribers received the event
    assert len(target_events) >= 1

    # If servers are different, other server should not receive it
    if server_name != other_server:
        assert len(other_events) == 0

    notifier.unsubscribe(sub1)
    notifier.unsubscribe(sub2)


@settings(max_examples=100)
@given(
    server_name=server_names,
    tool_name=tool_names,
    phase=phases,
    elapsed=elapsed_seconds,
)
def test_property_13_unsubscribe_stops_delivery(
    server_name: str,
    tool_name: str,
    phase: str,
    elapsed: float,
) -> None:
    """After unsubscribe, the callback SHALL NOT receive further events.

    **Validates: Requirements 6.4**
    """
    notifier = ProgressNotifier()
    received_events: list[ProgressEvent] = []

    sub_id = notifier.subscribe(server_name, received_events.append)
    notifier.unsubscribe(sub_id)

    event = ProgressEvent(
        server_name=server_name,
        tool_name=tool_name,
        progress_pct=50.0,
        phase=phase,
        elapsed_seconds=elapsed,
        timestamp=datetime.now(UTC),
    )
    notifier.emit(event)

    assert len(received_events) == 0
