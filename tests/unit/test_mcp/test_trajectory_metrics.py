"""
Tests for trajectory metrics tracking.

Validates: Requirements 11.1, 11.2, 11.3, 11.4
"""

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from deepr.mcp.evaluation.metrics import (
    MetricsTracker,
    StepType,
    TrajectoryMetrics,
    TrajectoryStep,
    calculate_citation_accuracy,
    calculate_context_economy,
    calculate_efficiency,
    detect_hallucinations,
)


class TestTrajectoryStep:
    """Tests for TrajectoryStep dataclass."""

    def test_create_tool_call_step(self):
        """Create a tool call step."""
        step = TrajectoryStep(
            step_type=StepType.TOOL_CALL,
            tool_name="deepr_research",
            parameters={"prompt": "test query"},
            tokens_used=100,
        )

        assert step.step_type == StepType.TOOL_CALL
        assert step.tool_name == "deepr_research"
        assert step.parameters == {"prompt": "test query"}
        assert step.tokens_used == 100
        assert step.success is True

    def test_step_to_dict(self):
        """Step converts to dictionary."""
        step = TrajectoryStep(
            step_type=StepType.TOOL_CALL,
            tool_name="test_tool",
            parameters={"key": "value"},
            tokens_used=50,
        )

        result = step.to_dict()

        assert result["step_type"] == "tool_call"
        assert result["tool_name"] == "test_tool"
        assert result["parameters"] == {"key": "value"}
        assert result["tokens_used"] == 50
        assert result["success"] is True

    def test_error_step(self):
        """Create an error step."""
        step = TrajectoryStep(
            step_type=StepType.ERROR,
            tool_name="failed_tool",
            success=False,
            error_message="Connection timeout",
        )

        assert step.success is False
        assert step.error_message == "Connection timeout"


class TestTrajectoryMetrics:
    """Tests for TrajectoryMetrics dataclass."""

    def test_default_metrics(self):
        """Default metrics have sensible values."""
        metrics = TrajectoryMetrics()

        assert metrics.efficiency == 1.0
        assert metrics.citation_accuracy == 1.0
        assert metrics.hallucination_rate == 0.0
        assert metrics.tokens_per_task == 0.0

    def test_metrics_to_dict(self):
        """Metrics convert to dictionary."""
        metrics = TrajectoryMetrics(
            total_steps=10,
            optimal_steps=8,
            efficiency=0.8,
            total_claims=20,
            cited_claims=19,
            citation_accuracy=0.95,
        )

        result = metrics.to_dict()

        assert result["efficiency"]["total_steps"] == 10
        assert result["efficiency"]["efficiency"] == 0.8
        assert result["citation_accuracy"]["accuracy"] == 0.95

    def test_passes_targets_all_pass(self):
        """Metrics that meet all targets pass."""
        metrics = TrajectoryMetrics(
            efficiency=0.95,
            citation_accuracy=0.98,
            hallucination_rate=0.005,
            tokens_per_task=5000,
        )

        passes, failures = metrics.passes_targets()

        assert passes is True
        assert failures == []

    def test_passes_targets_efficiency_fail(self):
        """Low efficiency fails target."""
        metrics = TrajectoryMetrics(
            efficiency=0.5,
            citation_accuracy=0.98,
            hallucination_rate=0.005,
            tokens_per_task=5000,
        )

        passes, failures = metrics.passes_targets(efficiency_target=0.9)

        assert passes is False
        assert len(failures) == 1
        assert "Efficiency" in failures[0]

    def test_passes_targets_multiple_failures(self):
        """Multiple failures are all reported."""
        metrics = TrajectoryMetrics(
            efficiency=0.5,
            citation_accuracy=0.5,
            hallucination_rate=0.1,
            tokens_per_task=50000,
        )

        passes, failures = metrics.passes_targets()

        assert passes is False
        assert len(failures) == 4


class TestMetricsTracker:
    """Tests for MetricsTracker class."""

    def test_record_tool_call(self):
        """Record a tool call step."""
        tracker = MetricsTracker()

        tracker.record_tool_call(
            tool_name="deepr_research",
            parameters={"prompt": "test"},
            tokens=100,
        )

        assert len(tracker.steps) == 1
        assert tracker.steps[0].tool_name == "deepr_research"
        assert tracker.steps[0].tokens_used == 100

    def test_record_resource_read(self):
        """Record a resource read step."""
        tracker = MetricsTracker()

        tracker.record_resource_read(
            resource_uri="deepr://campaigns/123/status",
            tokens=50,
        )

        assert len(tracker.steps) == 1
        assert tracker.steps[0].step_type == StepType.RESOURCE_READ

    def test_record_elicitation(self):
        """Record an elicitation step."""
        tracker = MetricsTracker()

        tracker.record_elicitation(
            elicitation_type="budget_decision",
            response="APPROVE_OVERRIDE",
            tokens=30,
        )

        assert len(tracker.steps) == 1
        assert tracker.steps[0].step_type == StepType.ELICITATION

    def test_calculate_metrics(self):
        """Calculate metrics from recorded steps."""
        tracker = MetricsTracker(golden_path=["tool_a", "tool_b"])

        tracker.record_tool_call("tool_a", {}, tokens=100)
        tracker.record_tool_call("tool_b", {}, tokens=100)
        tracker.record_tool_call("tool_c", {}, tokens=100)  # Extra step

        metrics = tracker.calculate_metrics()

        assert metrics.total_steps == 3
        assert metrics.optimal_steps == 2
        assert metrics.efficiency == pytest.approx(2 / 3, rel=0.01)
        assert metrics.total_tokens == 300

    def test_reset_clears_steps(self):
        """Reset clears all recorded steps."""
        tracker = MetricsTracker()
        tracker.record_tool_call("test", {})

        tracker.reset()

        assert len(tracker.steps) == 0

    def test_register_schema_for_hallucination_detection(self):
        """Register schema enables hallucination detection."""
        tracker = MetricsTracker()
        tracker.register_schema("test_tool", {"valid_param"})

        tracker.record_tool_call(
            "test_tool",
            {"valid_param": "ok", "invalid_param": "bad"},
        )

        metrics = tracker.calculate_metrics()

        assert metrics.hallucinated_parameters == 1
        assert metrics.total_parameters == 2


class TestCalculateEfficiency:
    """Tests for efficiency calculation."""

    def test_perfect_efficiency(self):
        """Optimal path matches actual steps."""
        steps = [
            TrajectoryStep(StepType.TOOL_CALL, tool_name="a"),
            TrajectoryStep(StepType.TOOL_CALL, tool_name="b"),
        ]
        golden = ["a", "b"]

        efficiency = calculate_efficiency(steps, golden)

        assert efficiency == 1.0

    def test_extra_steps_reduce_efficiency(self):
        """Extra steps reduce efficiency."""
        steps = [
            TrajectoryStep(StepType.TOOL_CALL, tool_name="a"),
            TrajectoryStep(StepType.TOOL_CALL, tool_name="b"),
            TrajectoryStep(StepType.TOOL_CALL, tool_name="c"),
            TrajectoryStep(StepType.TOOL_CALL, tool_name="d"),
        ]
        golden = ["a", "b"]

        efficiency = calculate_efficiency(steps, golden)

        assert efficiency == 0.5

    def test_empty_steps_perfect_efficiency(self):
        """Empty steps have perfect efficiency."""
        efficiency = calculate_efficiency([], [])
        assert efficiency == 1.0

    def test_no_golden_path_uses_actual(self):
        """Without golden path, efficiency is 1.0."""
        steps = [
            TrajectoryStep(StepType.TOOL_CALL, tool_name="a"),
        ]

        efficiency = calculate_efficiency(steps, [])

        assert efficiency == 1.0

    @given(st.integers(min_value=1, max_value=100))
    @settings(max_examples=50)
    def test_efficiency_never_exceeds_one(self, num_steps):
        """Efficiency is always <= 1.0."""
        steps = [TrajectoryStep(StepType.TOOL_CALL, tool_name=f"step_{i}") for i in range(num_steps)]
        golden = [f"step_{i}" for i in range(num_steps * 2)]  # More optimal steps

        efficiency = calculate_efficiency(steps, golden)

        assert efficiency <= 1.0


class TestCalculateCitationAccuracy:
    """Tests for citation accuracy calculation."""

    def test_all_claims_cited(self):
        """All claims have citations."""
        text = "The market grew 50% [1]. Revenue was $1M [2]."

        accuracy, cited, total = calculate_citation_accuracy(text)

        assert accuracy == 1.0
        assert cited == 2

    def test_no_citations(self):
        """Text with claims but no citations."""
        text = "The market grew 50%. Revenue was $1M."

        accuracy, cited, total = calculate_citation_accuracy(text)

        assert cited == 0
        assert accuracy == 0.0

    def test_empty_text(self):
        """Empty text has perfect accuracy."""
        accuracy, cited, total = calculate_citation_accuracy("")

        assert accuracy == 1.0
        assert cited == 0
        assert total == 0

    def test_override_total_claims(self):
        """Can override total claims count."""
        text = "Some fact [1]."

        accuracy, cited, total = calculate_citation_accuracy(text, total_claims=10)

        assert total == 10
        assert cited == 1
        assert accuracy == 0.1


class TestDetectHallucinations:
    """Tests for hallucination detection."""

    def test_no_hallucinations(self):
        """All parameters are valid."""
        steps = [
            TrajectoryStep(
                StepType.TOOL_CALL,
                tool_name="test_tool",
                parameters={"valid_a": 1, "valid_b": 2},
            ),
        ]
        schemas = {"test_tool": {"valid_a", "valid_b"}}

        result = detect_hallucinations(steps, schemas)

        assert result["hallucinated"] == 0
        assert result["rate"] == 0.0

    def test_hallucinated_parameter(self):
        """Detect invented parameter."""
        steps = [
            TrajectoryStep(
                StepType.TOOL_CALL,
                tool_name="test_tool",
                parameters={"valid": 1, "invented": 2},
            ),
        ]
        schemas = {"test_tool": {"valid"}}

        result = detect_hallucinations(steps, schemas)

        assert result["hallucinated"] == 1
        assert result["total"] == 2
        assert result["rate"] == 0.5

    def test_unknown_tool_skipped(self):
        """Unknown tools are skipped."""
        steps = [
            TrajectoryStep(
                StepType.TOOL_CALL,
                tool_name="unknown_tool",
                parameters={"any": 1},
            ),
        ]
        schemas = {}

        result = detect_hallucinations(steps, schemas)

        assert result["total"] == 0

    def test_non_tool_steps_skipped(self):
        """Non-tool steps are skipped."""
        steps = [
            TrajectoryStep(StepType.RESOURCE_READ, tool_name="uri"),
            TrajectoryStep(StepType.ELICITATION, tool_name="budget"),
        ]
        schemas = {"uri": set(), "budget": set()}

        result = detect_hallucinations(steps, schemas)

        assert result["total"] == 0


class TestCalculateContextEconomy:
    """Tests for context economy calculation."""

    def test_tokens_per_task(self):
        """Calculate tokens per task."""
        result = calculate_context_economy(1000, 10)
        assert result == 100.0

    def test_zero_tasks(self):
        """Zero tasks returns total tokens."""
        result = calculate_context_economy(500, 0)
        assert result == 500.0

    def test_zero_tokens_zero_tasks(self):
        """Zero tokens and tasks returns 0."""
        result = calculate_context_economy(0, 0)
        assert result == 0.0

    @given(
        st.integers(min_value=0, max_value=100000),
        st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=50)
    def test_economy_is_non_negative(self, tokens, tasks):
        """Context economy is always non-negative."""
        result = calculate_context_economy(tokens, tasks)
        assert result >= 0


class TestPropertyBased:
    """Property-based tests for trajectory metrics."""

    @given(
        st.lists(
            st.sampled_from(["a", "b", "c", "d", "e"]),
            min_size=0,
            max_size=20,
        )
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_efficiency_bounded(self, tool_names):
        """Efficiency is always between 0 and 1."""
        steps = [TrajectoryStep(StepType.TOOL_CALL, tool_name=name) for name in tool_names]
        golden = ["a", "b"]

        efficiency = calculate_efficiency(steps, golden)

        assert 0.0 <= efficiency <= 1.0

    @given(st.text(min_size=0, max_size=500))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_citation_accuracy_bounded(self, text):
        """Citation accuracy is always between 0 and 1."""
        accuracy, _, _ = calculate_citation_accuracy(text)
        assert 0.0 <= accuracy <= 1.0

    @given(
        st.lists(
            st.fixed_dictionaries(
                {
                    "tool": st.sampled_from(["tool_a", "tool_b"]),
                    "params": st.dictionaries(
                        st.sampled_from(["valid", "invalid", "unknown"]),
                        st.integers(),
                        max_size=3,
                    ),
                }
            ),
            max_size=10,
        )
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_hallucination_rate_bounded(self, tool_calls):
        """Hallucination rate is always between 0 and 1."""
        steps = [
            TrajectoryStep(
                StepType.TOOL_CALL,
                tool_name=tc["tool"],
                parameters=tc["params"],
            )
            for tc in tool_calls
        ]
        schemas = {
            "tool_a": {"valid"},
            "tool_b": {"valid", "other"},
        }

        result = detect_hallucinations(steps, schemas)

        assert 0.0 <= result["rate"] <= 1.0
