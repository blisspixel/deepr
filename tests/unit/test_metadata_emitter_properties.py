"""Property-based tests for MetadataEmitter.

Tests the metadata emission completeness property:
- All started tasks have metadata recorded
- Cost tracking is accurate and consistent
- Timeline is always sorted by start time
- Serialization roundtrip preserves all data
- Parent-child relationships are maintained

Requirements: 18.1, 18.2
Task: 20.5
"""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from deepr.observability.metadata import (
    MetadataEmitter,
    TaskMetadata,
)

# =============================================================================
# Test Strategies
# =============================================================================

# Valid task types
task_types = st.sampled_from(
    ["research", "chat", "synthesis", "fact_check", "planning", "documentation", "strategy", "sub_search"]
)

# Valid prompts (non-empty strings)
prompts = st.text(min_size=0, max_size=500).filter(lambda x: x == x.strip())

# Valid model names
model_names = st.sampled_from(
    ["gpt-4o", "gpt-5", "grok-4-fast", "o4-mini-deep-research", "claude-3-opus", "gemini-pro"]
)

# Valid provider names
provider_names = st.sampled_from(["openai", "xai", "anthropic", "google", "azure"])

# Non-negative costs
costs = st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)

# Non-negative token counts
token_counts = st.integers(min_value=0, max_value=100000)

# Context source names
context_sources = st.lists(
    st.text(min_size=1, max_size=50).filter(lambda x: x.strip() == x and len(x) > 0), min_size=0, max_size=10
)

# Task statuses
task_statuses = st.sampled_from(["running", "completed", "failed", "partial"])


# =============================================================================
# Unit Tests for TaskMetadata
# =============================================================================


class TestTaskMetadataUnit:
    """Unit tests for TaskMetadata dataclass."""

    def test_default_values(self):
        """Test TaskMetadata has correct default values."""
        task = TaskMetadata(task_id="test-1", task_type="research")

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

    def test_duration_ms_none_when_running(self):
        """Test duration_ms is None when task is still running."""
        task = TaskMetadata(task_id="test-2", task_type="chat")
        assert task.duration_ms is None

    def test_duration_ms_calculated_when_complete(self):
        """Test duration_ms is calculated when task is complete."""
        start = datetime.utcnow()
        end = start + timedelta(milliseconds=2500)

        task = TaskMetadata(task_id="test-3", task_type="synthesis", start_time=start, end_time=end)

        assert task.duration_ms is not None
        assert abs(task.duration_ms - 2500.0) < 1.0

    def test_to_dict_includes_all_fields(self):
        """Test to_dict includes all required fields."""
        task = TaskMetadata(task_id="test-4", task_type="research")
        data = task.to_dict()

        required_fields = [
            "task_id",
            "task_type",
            "prompt",
            "model",
            "provider",
            "tokens_input",
            "tokens_output",
            "cost",
            "context_sources",
            "start_time",
            "end_time",
            "status",
            "error",
            "parent_task_id",
            "duration_ms",
        ]

        for field in required_fields:
            assert field in data


# =============================================================================
# Property Tests for TaskMetadata
# =============================================================================


class TestTaskMetadataProperties:
    """Property tests for TaskMetadata."""

    @given(
        task_id=st.text(min_size=1, max_size=50),
        task_type=task_types,
        prompt=prompts,
        model=model_names,
        provider=provider_names,
        tokens_input=token_counts,
        tokens_output=token_counts,
        cost=costs,
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_task_metadata_stores_all_values(
        self, task_id, task_type, prompt, model, provider, tokens_input, tokens_output, cost
    ):
        """Property: TaskMetadata stores all provided values correctly."""
        assume(len(task_id.strip()) > 0)

        task = TaskMetadata(
            task_id=task_id,
            task_type=task_type,
            prompt=prompt,
            model=model,
            provider=provider,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            cost=cost,
        )

        assert task.task_id == task_id
        assert task.task_type == task_type
        assert task.prompt == prompt
        assert task.model == model
        assert task.provider == provider
        assert task.tokens_input == tokens_input
        assert task.tokens_output == tokens_output
        assert abs(task.cost - cost) < 0.0001

    @given(
        task_type=task_types,
        sources=context_sources,
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_context_sources_stored_correctly(self, task_type, sources):
        """Property: Context sources are stored as provided."""
        task = TaskMetadata(
            task_id="test",
            task_type=task_type,
            context_sources=sources,
        )

        assert task.context_sources == sources
        assert len(task.context_sources) == len(sources)

    @given(
        duration_ms=st.integers(min_value=0, max_value=3600000),  # Up to 1 hour
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_duration_calculation_accuracy(self, duration_ms):
        """Property: Duration calculation is accurate."""
        start = datetime.utcnow()
        end = start + timedelta(milliseconds=duration_ms)

        task = TaskMetadata(
            task_id="test",
            task_type="research",
            start_time=start,
            end_time=end,
        )

        assert task.duration_ms is not None
        # Allow 1ms tolerance for floating point
        assert abs(task.duration_ms - duration_ms) < 1.0

    @given(
        task_type=task_types,
        cost=costs,
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_to_dict_roundtrip(self, task_type, cost):
        """Property: to_dict produces valid JSON-serializable data."""
        task = TaskMetadata(
            task_id="test",
            task_type=task_type,
            cost=cost,
        )
        task.end_time = task.start_time + timedelta(seconds=1)

        data = task.to_dict()

        # Should be JSON serializable
        json_str = json.dumps(data)
        restored = json.loads(json_str)

        assert restored["task_id"] == task.task_id
        assert restored["task_type"] == task.task_type
        assert abs(restored["cost"] - cost) < 0.0001


# =============================================================================
# Property Tests for MetadataEmitter
# =============================================================================


class TestMetadataEmitterProperties:
    """Property tests for MetadataEmitter."""

    @given(
        task_type=task_types,
        prompt=prompts,
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_start_task_creates_metadata(self, task_type, prompt):
        """Property: start_task always creates task metadata."""
        emitter = MetadataEmitter()

        op = emitter.start_task(task_type, prompt)

        assert len(emitter.tasks) == 1
        assert emitter.tasks[0].task_type == task_type
        assert emitter.tasks[0].prompt == prompt
        assert emitter.tasks[0].status == "running"

    @given(
        num_tasks=st.integers(min_value=1, max_value=20),
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_all_tasks_recorded(self, num_tasks):
        """Property: All started tasks are recorded in the emitter."""
        emitter = MetadataEmitter()

        for i in range(num_tasks):
            with emitter.operation(f"task_{i}") as op:
                op.set_cost(0.01)

        assert len(emitter.tasks) == num_tasks

    @given(
        costs_list=st.lists(costs, min_size=1, max_size=20),
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_total_cost_is_sum_of_task_costs(self, costs_list):
        """Property: Total cost equals sum of all task costs."""
        emitter = MetadataEmitter()

        for cost in costs_list:
            with emitter.operation("research") as op:
                op.set_cost(cost)

        expected_total = sum(costs_list)
        actual_total = emitter.get_total_cost()

        # Allow small floating point tolerance
        assert abs(actual_total - expected_total) < 0.001

    @given(
        task_types_list=st.lists(task_types, min_size=1, max_size=10),
        cost=costs,
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_cost_breakdown_sums_correctly(self, task_types_list, cost):
        """Property: Cost breakdown sums to total cost."""
        emitter = MetadataEmitter()

        for task_type in task_types_list:
            with emitter.operation(task_type) as op:
                op.set_cost(cost)

        breakdown = emitter.get_cost_breakdown()
        breakdown_total = sum(breakdown.values())
        total_cost = emitter.get_total_cost()

        assert abs(breakdown_total - total_cost) < 0.001

    @given(
        num_tasks=st.integers(min_value=2, max_value=10),
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_timeline_sorted_by_start_time(self, num_tasks):
        """Property: Timeline is always sorted by start time."""
        emitter = MetadataEmitter()

        for i in range(num_tasks):
            with emitter.operation(f"task_{i}") as op:
                op.set_cost(0.01)

        timeline = emitter.get_timeline()

        # Verify sorted order
        for i in range(len(timeline) - 1):
            assert timeline[i]["start_time"] <= timeline[i + 1]["start_time"]

    @given(
        task_type=task_types,
        cost=costs,
        model=model_names,
        provider=provider_names,
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_operation_context_sets_all_metadata(self, task_type, cost, model, provider):
        """Property: OperationContext correctly sets all metadata."""
        emitter = MetadataEmitter()

        with emitter.operation(task_type) as op:
            op.set_cost(cost)
            op.set_model(model, provider)
            op.set_tokens(100, 200)

        task = emitter.tasks[0]
        assert task.task_type == task_type
        assert abs(task.cost - cost) < 0.0001
        assert task.model == model
        assert task.provider == provider
        assert task.tokens_input == 100
        assert task.tokens_output == 200


class TestMetadataEmitterPersistenceProperties:
    """Property tests for MetadataEmitter persistence."""

    @given(
        task_type=task_types,
        cost=costs,
        model=model_names,
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_save_load_roundtrip_preserves_data(self, task_type, cost, model):
        """Property: Save/load roundtrip preserves all task data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "trace.json"

            # Create and save
            emitter1 = MetadataEmitter()
            with emitter1.operation(task_type) as op:
                op.set_cost(cost)
                op.set_model(model, "openai")
            emitter1.save_trace(path)

            # Load and verify
            emitter2 = MetadataEmitter.load_trace(path)

            assert len(emitter2.tasks) == 1
            assert emitter2.tasks[0].task_type == task_type
            assert abs(emitter2.tasks[0].cost - cost) < 0.0001
            assert emitter2.tasks[0].model == model

    @given(
        num_tasks=st.integers(min_value=1, max_value=10),
        cost=costs,
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_save_load_preserves_task_count(self, num_tasks, cost):
        """Property: Save/load preserves the number of tasks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "trace.json"

            # Create and save
            emitter1 = MetadataEmitter()
            for i in range(num_tasks):
                with emitter1.operation(f"task_{i}") as op:
                    op.set_cost(cost)
            emitter1.save_trace(path)

            # Load and verify
            emitter2 = MetadataEmitter.load_trace(path)

            assert len(emitter2.tasks) == num_tasks

    @given(
        costs_list=st.lists(costs, min_size=1, max_size=10),
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_save_load_preserves_total_cost(self, costs_list):
        """Property: Save/load preserves total cost."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "trace.json"

            # Create and save
            emitter1 = MetadataEmitter()
            for cost in costs_list:
                with emitter1.operation("research") as op:
                    op.set_cost(cost)
            original_total = emitter1.get_total_cost()
            emitter1.save_trace(path)

            # Load and verify
            emitter2 = MetadataEmitter.load_trace(path)
            loaded_total = emitter2.get_total_cost()

            assert abs(loaded_total - original_total) < 0.001


class TestMetadataEmitterNestedOperationsProperties:
    """Property tests for nested operations."""

    @given(
        parent_type=task_types,
        child_type=task_types,
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_nested_operations_track_parent(self, parent_type, child_type):
        """Property: Nested operations correctly track parent-child relationship."""
        emitter = MetadataEmitter()

        with emitter.operation(parent_type) as parent_op:
            parent_id = parent_op.metadata.task_id

            with emitter.operation(child_type) as child_op:
                child_parent_id = child_op.metadata.parent_task_id

        # Child should reference parent
        assert child_parent_id == parent_id

    @given(
        depth=st.integers(min_value=1, max_value=5),
    )
    @settings(
        max_examples=10,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_deeply_nested_operations(self, depth):
        """Property: Deeply nested operations maintain correct hierarchy."""
        emitter = MetadataEmitter()

        def create_nested(current_depth, parent_id=None):
            if current_depth == 0:
                return

            with emitter.operation(f"level_{current_depth}") as op:
                if parent_id is not None:
                    assert op.metadata.parent_task_id == parent_id
                create_nested(current_depth - 1, op.metadata.task_id)

        create_nested(depth)

        assert len(emitter.tasks) == depth


class TestMetadataEmitterContextSourcesProperties:
    """Property tests for context source tracking."""

    @given(
        sources=context_sources,
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_context_sources_recorded(self, sources):
        """Property: All context sources are recorded."""
        emitter = MetadataEmitter()

        with emitter.operation("research") as op:
            for source in sources:
                op.add_context_source(source)

        task = emitter.tasks[0]
        assert len(task.context_sources) == len(sources)
        for source in sources:
            assert source in task.context_sources

    @given(
        num_tasks=st.integers(min_value=1, max_value=5),
        sources_per_task=st.integers(min_value=0, max_value=5),
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_context_lineage_completeness(self, num_tasks, sources_per_task):
        """Property: Context lineage includes all tasks with sources."""
        emitter = MetadataEmitter()

        tasks_with_sources = 0
        for i in range(num_tasks):
            with emitter.operation(f"task_{i}") as op:
                if sources_per_task > 0:
                    for j in range(sources_per_task):
                        op.add_context_source(f"source_{i}_{j}")
                    tasks_with_sources += 1

        lineage = emitter.get_context_lineage()

        # Lineage should have entry for each task with sources
        assert len(lineage) == tasks_with_sources


class TestMetadataEmitterErrorHandlingProperties:
    """Property tests for error handling."""

    @given(
        error_message=st.text(min_size=1, max_size=200),
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_failed_task_records_error(self, error_message):
        """Property: Failed tasks record the error message."""
        assume(len(error_message.strip()) > 0)

        emitter = MetadataEmitter()

        try:
            with emitter.operation("research") as op:
                raise ValueError(error_message)
        except ValueError:
            pass

        task = emitter.tasks[0]
        assert task.status == "failed"
        assert task.error == error_message

    @given(
        task_type=task_types,
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_completed_task_has_end_time(self, task_type):
        """Property: Completed tasks always have an end time."""
        emitter = MetadataEmitter()

        with emitter.operation(task_type) as op:
            op.set_cost(0.01)

        task = emitter.tasks[0]
        assert task.status == "completed"
        assert task.end_time is not None
        assert task.end_time >= task.start_time


class TestMetadataEmitterInvariantsProperties:
    """Property tests for emitter invariants."""

    @given(
        num_tasks=st.integers(min_value=0, max_value=20),
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_task_count_matches_operations(self, num_tasks):
        """Property: Task count always matches number of operations."""
        emitter = MetadataEmitter()

        for i in range(num_tasks):
            with emitter.operation(f"task_{i}"):
                pass

        assert len(emitter.tasks) == num_tasks
        assert len(emitter.get_timeline()) == num_tasks

    @given(
        costs_list=st.lists(costs, min_size=0, max_size=20),
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_cost_is_non_negative(self, costs_list):
        """Property: Total cost is always non-negative."""
        emitter = MetadataEmitter()

        for cost in costs_list:
            with emitter.operation("research") as op:
                op.set_cost(cost)

        assert emitter.get_total_cost() >= 0.0

    def test_empty_emitter_invariants(self):
        """Test empty emitter maintains invariants."""
        emitter = MetadataEmitter()

        assert len(emitter.tasks) == 0
        assert emitter.get_total_cost() == 0.0
        assert emitter.get_timeline() == []
        assert emitter.get_cost_breakdown() == {}
        assert emitter.get_context_lineage() == {}

    @given(
        task_type=task_types,
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_trace_context_always_exists(self, task_type):
        """Property: Trace context is always available."""
        emitter = MetadataEmitter()

        assert emitter.trace_context is not None
        assert emitter.trace_context.trace_id is not None

        with emitter.operation(task_type):
            pass

        assert emitter.trace_context is not None
