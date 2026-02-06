"""Tests for the traces module.

Tests the TraceContext, Span, and related tracing functionality
for observability and cost tracking.
"""

import tempfile
import threading
import time
from pathlib import Path

import pytest

from deepr.observability.traces import Span, SpanStatus, TraceContext, get_or_create_trace


class TestSpan:
    """Tests for Span class."""

    def test_create_span(self):
        """Test creating a span with basic attributes."""
        span = Span(span_id="span-001", trace_id="trace-001", parent_span_id=None, name="test_operation")

        assert span.span_id == "span-001"
        assert span.trace_id == "trace-001"
        assert span.parent_span_id is None
        assert span.name == "test_operation"
        assert span.status == SpanStatus.RUNNING
        assert span.cost == 0.0

    def test_span_set_attribute(self):
        """Test setting attributes on a span."""
        span = Span(span_id="span-001", trace_id="trace-001", parent_span_id=None, name="test")

        span.set_attribute("query", "test query")
        span.set_attribute("count", 42)
        span.set_attribute("nested", {"key": "value"})

        assert span.attributes["query"] == "test query"
        assert span.attributes["count"] == 42
        assert span.attributes["nested"] == {"key": "value"}

    def test_span_add_event(self):
        """Test adding events to a span."""
        span = Span(span_id="span-001", trace_id="trace-001", parent_span_id=None, name="test")

        span.add_event("started_processing")
        span.add_event("found_result", {"count": 5})

        assert len(span.events) == 2
        assert span.events[0]["name"] == "started_processing"
        assert span.events[1]["name"] == "found_result"
        assert span.events[1]["attributes"]["count"] == 5

    def test_span_set_cost(self):
        """Test setting cost on a span."""
        span = Span(span_id="span-001", trace_id="trace-001", parent_span_id=None, name="test")

        span.set_cost(0.15)
        assert span.cost == 0.15

    def test_span_complete(self):
        """Test completing a span."""
        span = Span(span_id="span-001", trace_id="trace-001", parent_span_id=None, name="test")

        assert span.status == SpanStatus.RUNNING
        assert span.end_time is None

        span.complete()

        assert span.status == SpanStatus.COMPLETED
        assert span.end_time is not None

    def test_span_fail(self):
        """Test failing a span."""
        span = Span(span_id="span-001", trace_id="trace-001", parent_span_id=None, name="test")

        span.fail("Something went wrong")

        assert span.status == SpanStatus.FAILED
        assert span.end_time is not None
        assert span.attributes["error"] == "Something went wrong"

    def test_span_duration(self):
        """Test span duration calculation."""
        span = Span(span_id="span-001", trace_id="trace-001", parent_span_id=None, name="test")

        # Duration is None while running
        assert span.duration_ms is None

        # Wait a bit and complete
        time.sleep(0.01)  # 10ms
        span.complete()

        # Duration should be positive
        assert span.duration_ms is not None
        assert span.duration_ms > 0

    def test_span_to_dict(self):
        """Test span serialization."""
        span = Span(span_id="span-001", trace_id="trace-001", parent_span_id="parent-001", name="test")
        span.set_attribute("key", "value")
        span.set_cost(0.05)
        span.complete()

        d = span.to_dict()

        assert d["span_id"] == "span-001"
        assert d["trace_id"] == "trace-001"
        assert d["parent_span_id"] == "parent-001"
        assert d["name"] == "test"
        assert d["status"] == "completed"
        assert d["attributes"]["key"] == "value"
        assert d["cost"] == 0.05
        assert d["duration_ms"] is not None


class TestTraceContext:
    """Tests for TraceContext class."""

    def test_create_trace_context(self):
        """Test creating a trace context."""
        ctx = TraceContext.create()

        assert ctx.trace_id is not None
        assert len(ctx.spans) == 0
        assert ctx.current_span_id is None

    def test_start_and_end_span(self):
        """Test starting and ending spans."""
        ctx = TraceContext.create()

        span = ctx.start_span("operation")

        assert len(ctx.spans) == 1
        assert ctx.current_span_id == span.span_id

        ctx.end_span(span)

        assert span.status == SpanStatus.COMPLETED
        assert ctx.current_span_id is None

    def test_nested_spans(self):
        """Test nested span creation."""
        ctx = TraceContext.create()

        parent = ctx.start_span("parent")
        child = ctx.start_span("child")

        # Child should have parent as parent_span_id
        assert child.parent_span_id == parent.span_id

        ctx.end_span(child)
        ctx.end_span(parent)

        assert len(ctx.spans) == 2

    def test_span_context_manager(self):
        """Test span context manager."""
        ctx = TraceContext.create()

        with ctx.span("operation") as span:
            span.set_attribute("test", True)

        assert len(ctx.spans) == 1
        assert ctx.spans[0].status == SpanStatus.COMPLETED
        assert ctx.spans[0].attributes["test"] is True

    def test_span_context_manager_with_exception(self):
        """Test span context manager handles exceptions."""
        ctx = TraceContext.create()

        with pytest.raises(ValueError):
            with ctx.span("failing_operation") as span:
                raise ValueError("Test error")

        assert len(ctx.spans) == 1
        assert ctx.spans[0].status == SpanStatus.FAILED
        assert "Test error" in ctx.spans[0].attributes.get("error", "")

    def test_get_root_spans(self):
        """Test getting root spans."""
        ctx = TraceContext.create()

        with ctx.span("root1"):
            with ctx.span("child1"):
                pass

        with ctx.span("root2"):
            pass

        roots = ctx.get_root_spans()

        assert len(roots) == 2
        assert all(s.parent_span_id is None for s in roots)

    def test_get_children(self):
        """Test getting child spans."""
        ctx = TraceContext.create()

        with ctx.span("parent") as parent:
            with ctx.span("child1"):
                pass
            with ctx.span("child2"):
                pass

        children = ctx.get_children(parent.span_id)

        assert len(children) == 2
        assert all(c.parent_span_id == parent.span_id for c in children)

    def test_total_cost(self):
        """Test total cost calculation."""
        ctx = TraceContext.create()

        with ctx.span("op1") as s1:
            s1.set_cost(0.10)

        with ctx.span("op2") as s2:
            s2.set_cost(0.05)

        assert ctx.get_total_cost() == pytest.approx(0.15, rel=0.01)

    def test_total_duration(self):
        """Test total duration calculation."""
        ctx = TraceContext.create()

        with ctx.span("op1"):
            time.sleep(0.01)

        with ctx.span("op2"):
            time.sleep(0.01)

        duration = ctx.get_total_duration_ms()

        assert duration is not None
        assert duration > 0

    def test_to_dict(self):
        """Test trace context serialization."""
        ctx = TraceContext.create()

        with ctx.span("operation") as span:
            span.set_cost(0.05)

        d = ctx.to_dict()

        assert d["trace_id"] == ctx.trace_id
        assert len(d["spans"]) == 1
        assert d["total_cost"] == 0.05
        assert d["total_duration_ms"] is not None

    def test_save_and_load(self):
        """Test saving and loading trace context."""
        ctx = TraceContext.create()

        with ctx.span("operation") as span:
            span.set_attribute("key", "value")
            span.set_cost(0.10)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "trace.json"
            ctx.save(path)

            loaded = TraceContext.load(path)

            assert loaded.trace_id == ctx.trace_id
            assert len(loaded.spans) == 1
            assert loaded.spans[0].attributes["key"] == "value"
            assert loaded.spans[0].cost == 0.10


class TestTraceContextThreadSafety:
    """Tests for thread safety of TraceContext."""

    def test_concurrent_span_creation(self):
        """Test that concurrent span creation is thread-safe."""
        ctx = TraceContext.create()
        errors = []

        def create_spans():
            try:
                for i in range(10):
                    with ctx.span(f"operation_{threading.current_thread().name}_{i}"):
                        time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=create_spans) for _ in range(5)]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(ctx.spans) == 50  # 5 threads * 10 spans each

    def test_thread_local_context(self):
        """Test that trace context is thread-local."""
        contexts = {}

        def create_context():
            ctx = TraceContext.create()
            contexts[threading.current_thread().name] = ctx.trace_id

        threads = [threading.Thread(target=create_context, name=f"thread_{i}") for i in range(3)]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # Each thread should have a unique trace_id
        trace_ids = list(contexts.values())
        assert len(set(trace_ids)) == 3


class TestGetOrCreateTrace:
    """Tests for get_or_create_trace helper."""

    def test_creates_new_trace(self):
        """Test that get_or_create_trace creates a new trace when none exists."""
        # Clear any existing context
        TraceContext._local.current = None

        ctx = get_or_create_trace()

        assert ctx is not None
        assert ctx.trace_id is not None

    def test_returns_existing_trace(self):
        """Test that get_or_create_trace returns existing trace."""
        ctx1 = TraceContext.create()
        ctx2 = get_or_create_trace()

        assert ctx1.trace_id == ctx2.trace_id


class TestSpanStatusEnum:
    """Tests for SpanStatus enum."""

    def test_all_statuses_have_values(self):
        """Test that all span statuses have string values."""
        for status in SpanStatus:
            assert isinstance(status.value, str)
            assert len(status.value) > 0

    def test_status_values_are_lowercase(self):
        """Test that status values are lowercase for consistency."""
        for status in SpanStatus:
            assert status.value == status.value.lower()
