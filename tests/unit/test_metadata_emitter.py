"""Tests for MetadataEmitter and related classes.

Tests cover:
- TaskMetadata: task tracking and serialization
- OperationContext: fluent interface for setting metadata
- MetadataEmitter: span tracking, timeline, cost breakdown, persistence
"""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from deepr.observability.metadata import (
    MetadataEmitter,
    TaskMetadata,
)
from deepr.observability.traces import TraceContext


class TestTaskMetadata:
    """Tests for TaskMetadata dataclass."""

    def test_initial_state(self):
        """New task metadata should have correct defaults."""
        task = TaskMetadata(
            task_id="task-001",
            task_type="research",
        )

        assert task.task_id == "task-001"
        assert task.task_type == "research"
        assert task.prompt == ""
        assert task.model == ""
        assert task.provider == ""
        assert task.tokens_input == 0
        assert task.tokens_output == 0
        assert task.cost == 0.0
        assert task.context_sources == []
        assert task.status == "running"
        assert task.error is None
        assert task.parent_task_id is None
        assert task.start_time is not None

    def test_with_all_fields(self):
        """Task metadata should store all fields correctly."""
        start = datetime.utcnow()
        end = start + timedelta(seconds=5)

        task = TaskMetadata(
            task_id="task-002",
            task_type="synthesis",
            prompt="Summarize the documents",
            model="gpt-4o",
            provider="openai",
            tokens_input=1000,
            tokens_output=500,
            cost=0.05,
            context_sources=["doc1.pdf", "doc2.pdf"],
            start_time=start,
            end_time=end,
            status="completed",
            parent_task_id="task-001",
        )

        assert task.prompt == "Summarize the documents"
        assert task.model == "gpt-4o"
        assert task.provider == "openai"
        assert task.tokens_input == 1000
        assert task.tokens_output == 500
        assert task.cost == 0.05
        assert len(task.context_sources) == 2
        assert task.status == "completed"
        assert task.parent_task_id == "task-001"

    def test_duration_ms_completed(self):
        """Duration should be calculated for completed tasks."""
        start = datetime.utcnow()
        end = start + timedelta(milliseconds=1500)

        task = TaskMetadata(
            task_id="task-003",
            task_type="chat",
            start_time=start,
            end_time=end,
        )

        assert task.duration_ms is not None
        assert abs(task.duration_ms - 1500.0) < 1.0  # Allow small float error

    def test_duration_ms_running(self):
        """Duration should be None for running tasks."""
        task = TaskMetadata(
            task_id="task-004",
            task_type="research",
        )

        assert task.end_time is None
        assert task.duration_ms is None

    def test_to_dict_serialization(self):
        """Task metadata should serialize to dictionary correctly."""
        task = TaskMetadata(
            task_id="task-005",
            task_type="fact_check",
            prompt="Is the sky blue?",
            model="grok-4-fast",
            provider="xai",
            tokens_input=50,
            tokens_output=100,
            cost=0.01,
            context_sources=["source1"],
        )
        task.end_time = task.start_time + timedelta(seconds=2)
        task.status = "completed"

        data = task.to_dict()

        assert data["task_id"] == "task-005"
        assert data["task_type"] == "fact_check"
        assert data["prompt"] == "Is the sky blue?"
        assert data["model"] == "grok-4-fast"
        assert data["provider"] == "xai"
        assert data["tokens_input"] == 50
        assert data["tokens_output"] == 100
        assert data["cost"] == 0.01
        assert data["context_sources"] == ["source1"]
        assert data["status"] == "completed"
        assert "start_time" in data
        assert "end_time" in data
        assert "duration_ms" in data


class TestOperationContext:
    """Tests for OperationContext class."""

    @pytest.fixture
    def emitter(self):
        """Create a MetadataEmitter for testing."""
        return MetadataEmitter()

    def test_set_cost(self, emitter):
        """Setting cost should update both span and metadata."""
        op = emitter.start_task("research", "Test query")

        op.set_cost(0.15)

        assert op.metadata.cost == 0.15
        assert op.span.cost == 0.15

    def test_set_tokens(self, emitter):
        """Setting tokens should update metadata and span attributes."""
        op = emitter.start_task("chat", "Hello")

        op.set_tokens(input_tokens=100, output_tokens=200)

        assert op.metadata.tokens_input == 100
        assert op.metadata.tokens_output == 200

    def test_set_model(self, emitter):
        """Setting model should update metadata and span attributes."""
        op = emitter.start_task("synthesis", "Summarize")

        op.set_model(model="gpt-4o", provider="openai")

        assert op.metadata.model == "gpt-4o"
        assert op.metadata.provider == "openai"

    def test_add_context_source(self, emitter):
        """Adding context source should append to list."""
        op = emitter.start_task("research", "Query")

        op.add_context_source("doc1.pdf")
        op.add_context_source("doc2.pdf")

        assert len(op.metadata.context_sources) == 2
        assert "doc1.pdf" in op.metadata.context_sources
        assert "doc2.pdf" in op.metadata.context_sources

    def test_add_event(self, emitter):
        """Adding event should record timestamped event on span."""
        op = emitter.start_task("research", "Query")

        op.add_event("search_started", {"query": "test"})
        op.add_event("search_complete", {"results": 10})

        assert len(op.span.events) == 2

    def test_set_attribute(self, emitter):
        """Setting attribute should update span attributes."""
        op = emitter.start_task("chat", "Hello")

        op.set_attribute("custom_field", "custom_value")

        assert op.span.attributes.get("custom_field") == "custom_value"


class TestMetadataEmitter:
    """Tests for MetadataEmitter class."""

    def test_initialization(self):
        """Emitter should initialize with empty task list."""
        emitter = MetadataEmitter()

        assert len(emitter.tasks) == 0
        assert emitter.trace_context is not None

    def test_initialization_with_trace_context(self):
        """Emitter should accept existing trace context."""
        trace = TraceContext(trace_id="custom-trace-id")
        emitter = MetadataEmitter(trace_context=trace)

        assert emitter.trace_context.trace_id == "custom-trace-id"

    def test_start_task(self):
        """Starting task should create metadata and span."""
        emitter = MetadataEmitter()

        op = emitter.start_task("research", "What is quantum computing?")

        assert len(emitter.tasks) == 1
        assert emitter.tasks[0].task_type == "research"
        assert emitter.tasks[0].prompt == "What is quantum computing?"
        assert emitter.tasks[0].status == "running"
        assert op.span is not None

    def test_start_task_with_attributes(self):
        """Starting task with attributes should set them on span."""
        emitter = MetadataEmitter()

        op = emitter.start_task(
            "research",
            "Query",
            attributes={"priority": "high", "source": "user"},
        )

        assert op.span.attributes.get("priority") == "high"
        assert op.span.attributes.get("source") == "user"

    def test_complete_task(self):
        """Completing task should update status and end time."""
        emitter = MetadataEmitter()

        op = emitter.start_task("chat", "Hello")
        emitter.complete_task(op)

        assert op.metadata.status == "completed"
        assert op.metadata.end_time is not None

    def test_complete_task_custom_status(self):
        """Completing task with custom status should use that status."""
        emitter = MetadataEmitter()

        op = emitter.start_task("research", "Query")
        emitter.complete_task(op, status="partial")

        assert op.metadata.status == "partial"

    def test_fail_task(self):
        """Failing task should set error and failed status."""
        emitter = MetadataEmitter()

        op = emitter.start_task("synthesis", "Summarize")
        emitter.fail_task(op, error="API rate limit exceeded")

        assert op.metadata.status == "failed"
        assert op.metadata.error == "API rate limit exceeded"
        assert op.metadata.end_time is not None

    def test_operation_context_manager_success(self):
        """Operation context manager should complete task on success."""
        emitter = MetadataEmitter()

        with emitter.operation("research", prompt="Test query") as op:
            op.set_cost(0.05)
            op.set_tokens(100, 200)

        assert len(emitter.tasks) == 1
        assert emitter.tasks[0].status == "completed"
        assert emitter.tasks[0].cost == 0.05

    def test_operation_context_manager_failure(self):
        """Operation context manager should fail task on exception."""
        emitter = MetadataEmitter()

        with pytest.raises(ValueError):
            with emitter.operation("research", prompt="Test") as op:
                raise ValueError("Test error")

        assert len(emitter.tasks) == 1
        assert emitter.tasks[0].status == "failed"
        assert emitter.tasks[0].error == "Test error"

    def test_get_timeline(self):
        """Timeline should return tasks sorted by start time."""
        emitter = MetadataEmitter()

        # Create tasks (they'll have slightly different start times)
        op1 = emitter.start_task("research", "Query 1")
        op2 = emitter.start_task("chat", "Query 2")
        op3 = emitter.start_task("synthesis", "Query 3")

        emitter.complete_task(op1)
        emitter.complete_task(op2)
        emitter.complete_task(op3)

        timeline = emitter.get_timeline()

        assert len(timeline) == 3
        # Should be sorted by start_time
        for i in range(len(timeline) - 1):
            assert timeline[i]["start_time"] <= timeline[i + 1]["start_time"]

    def test_get_cost_breakdown(self):
        """Cost breakdown should group costs by task type."""
        emitter = MetadataEmitter()

        with emitter.operation("research") as op:
            op.set_cost(0.10)

        with emitter.operation("research") as op:
            op.set_cost(0.15)

        with emitter.operation("chat") as op:
            op.set_cost(0.05)

        breakdown = emitter.get_cost_breakdown()

        assert breakdown["research"] == 0.25  # 0.10 + 0.15
        assert breakdown["chat"] == 0.05

    def test_get_total_cost(self):
        """Total cost should sum all task costs."""
        emitter = MetadataEmitter()

        with emitter.operation("research") as op:
            op.set_cost(0.10)

        with emitter.operation("chat") as op:
            op.set_cost(0.05)

        with emitter.operation("synthesis") as op:
            op.set_cost(0.20)

        total = emitter.get_total_cost()

        # Use approximate comparison for floating point
        assert abs(total - 0.35) < 0.0001

    def test_get_context_lineage(self):
        """Context lineage should map tasks to their sources."""
        emitter = MetadataEmitter()

        with emitter.operation("research") as op:
            op.add_context_source("doc1.pdf")
            op.add_context_source("doc2.pdf")

        with emitter.operation("chat") as op:
            pass  # No context sources

        with emitter.operation("synthesis") as op:
            op.add_context_source("doc3.pdf")

        lineage = emitter.get_context_lineage()

        # Should only include tasks with context sources
        assert len(lineage) == 2
        # Check that sources are recorded
        for task_id, sources in lineage.items():
            assert len(sources) > 0

    def test_nested_operations(self):
        """Nested operations should track parent-child relationships."""
        emitter = MetadataEmitter()

        with emitter.operation("research", prompt="Main query") as parent_op:
            parent_op.set_cost(0.10)

            with emitter.operation("sub_search", prompt="Sub query") as child_op:
                child_op.set_cost(0.05)

        assert len(emitter.tasks) == 2

        # Find the child task
        child_task = next(t for t in emitter.tasks if t.task_type == "sub_search")
        assert child_task.parent_task_id is not None

    def test_save_trace(self):
        """Save trace should persist all data to JSON file."""
        emitter = MetadataEmitter()

        with emitter.operation("research", prompt="Test query") as op:
            op.set_cost(0.15)
            op.set_model("gpt-4o", "openai")
            op.add_context_source("test.pdf")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "trace.json"
            emitter.save_trace(path)

            assert path.exists()

            with open(path) as f:
                data = json.load(f)

            assert "trace_id" in data
            assert "tasks" in data
            assert "spans" in data
            assert "timeline" in data
            assert "cost_breakdown" in data
            assert "total_cost" in data
            assert "context_lineage" in data
            assert data["total_cost"] == 0.15

    def test_load_trace(self):
        """Load trace should restore emitter state from JSON file."""
        # Create and save a trace
        emitter1 = MetadataEmitter()

        with emitter1.operation("research", prompt="Test query") as op:
            op.set_cost(0.15)
            op.set_model("gpt-4o", "openai")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "trace.json"
            emitter1.save_trace(path)

            # Load into new emitter
            emitter2 = MetadataEmitter.load_trace(path)

            assert len(emitter2.tasks) == 1
            assert emitter2.tasks[0].task_type == "research"
            assert emitter2.tasks[0].cost == 0.15
            assert emitter2.tasks[0].model == "gpt-4o"

    def test_prompt_truncation(self):
        """Long prompts should be truncated in span attributes."""
        emitter = MetadataEmitter()

        long_prompt = "x" * 1000  # 1000 characters
        op = emitter.start_task("research", long_prompt)

        # Span attribute should be truncated to 500 chars
        prompt_attr = op.span.attributes.get("prompt", "")
        assert len(prompt_attr) <= 500


class TestMetadataEmitterEdgeCases:
    """Edge case tests for MetadataEmitter."""

    def test_empty_emitter_timeline(self):
        """Empty emitter should return empty timeline."""
        emitter = MetadataEmitter()

        timeline = emitter.get_timeline()

        assert timeline == []

    def test_empty_emitter_cost_breakdown(self):
        """Empty emitter should return empty cost breakdown."""
        emitter = MetadataEmitter()

        breakdown = emitter.get_cost_breakdown()

        assert breakdown == {}

    def test_empty_emitter_total_cost(self):
        """Empty emitter should return zero total cost."""
        emitter = MetadataEmitter()

        total = emitter.get_total_cost()

        assert total == 0.0

    def test_zero_cost_tasks(self):
        """Tasks with zero cost should be handled correctly."""
        emitter = MetadataEmitter()

        with emitter.operation("research") as op:
            op.set_cost(0.0)

        assert emitter.get_total_cost() == 0.0
        assert emitter.get_cost_breakdown()["research"] == 0.0

    def test_multiple_same_type_tasks(self):
        """Multiple tasks of same type should accumulate costs."""
        emitter = MetadataEmitter()

        for i in range(5):
            with emitter.operation("research") as op:
                op.set_cost(0.10)

        assert len(emitter.tasks) == 5
        assert emitter.get_total_cost() == 0.50
        assert emitter.get_cost_breakdown()["research"] == 0.50

    def test_save_creates_parent_directories(self):
        """Save should create parent directories if they don't exist."""
        emitter = MetadataEmitter()

        with emitter.operation("test") as op:
            op.set_cost(0.01)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nested" / "deep" / "trace.json"
            emitter.save_trace(path)

            assert path.exists()
