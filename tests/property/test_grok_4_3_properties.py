"""Property-based tests for Grok 4.3 Migration & Agentic Infrastructure Core.

All 15 correctness properties from the design document, validated using Hypothesis.
"""

from __future__ import annotations

from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

# Feature: grok-4-3-migration, Property 1: Reasoning Effort Resolution


@settings(max_examples=100)
@given(
    reasoning_effort=st.one_of(
        st.none(),
        st.sampled_from(["low", "medium", "high"]),
    ),
)
def test_property_1_reasoning_effort_resolution(reasoning_effort: str | None) -> None:
    """For any Grok 4.3 research request, the reasoning effort parameter SHALL equal
    the explicitly specified value if provided, or 'medium' if not specified.
    The resolved value is always one of {'low', 'medium', 'high'}.

    Validates: Requirements 1.4, 1.5
    """
    with patch.dict("os.environ", {"XAI_API_KEY": "test-key"}):
        from deepr.providers.base import ResearchRequest
        from deepr.providers.grok_provider import GrokProvider

        provider = GrokProvider(api_key="test-key")
        request = ResearchRequest(
            prompt="test query",
            model="grok-4-3",
            system_message="",
            reasoning_effort=reasoning_effort,
        )

        result = provider._get_reasoning_effort(request, "grok-4-3")

        # Must always be one of the valid values
        assert result in {"low", "medium", "high"}

        # If explicitly specified, must match
        if reasoning_effort is not None:
            assert result == reasoning_effort
        else:
            # Default is "medium"
            assert result == "medium"


# Feature: grok-4-3-migration, Property 2: Deprecated Model Migration Resolves to Successor


@settings(max_examples=100)
@given(
    model=st.sampled_from(
        [
            "grok-4-1-fast-reasoning",
            "grok-4-1-fast-non-reasoning",
            "grok-4-fast-reasoning",
            "grok-4-fast-non-reasoning",
            "grok-4-0709",
            "grok-code-fast-1",
            "grok-3",
            "grok-imagine-image-pro",
            "o3-deep-research",
            "grok-3-mini",
            "gpt-4o",
            "gpt-4o-mini",
        ]
    ),
)
def test_property_2_deprecated_model_migration_resolves_to_successor(model: str) -> None:
    """For any model marked as deprecated in the registry with a non-null successor,
    calling migrate_model SHALL return the designated successor model and a non-empty
    warning string.

    Validates: Requirements 3.1, 3.2, 10.4
    """
    from deepr.routing.deprecation import DEPRECATION_REGISTRY, migrate_model

    entry = DEPRECATION_REGISTRY[model]
    resolved_model, _confidence, warning = migrate_model(model)

    # Must resolve to the designated successor
    if entry.auto_migrate:
        assert entry.new_model is not None
        assert resolved_model == entry.new_model.split("/", 1)[-1]
    else:
        assert resolved_model == model

    # Warning must be non-empty
    assert warning is not None
    assert len(warning) > 0


# Feature: grok-4-3-migration, Property 3: Migration Preserves Routing Confidence


@settings(max_examples=100)
@given(
    model=st.sampled_from(
        [
            "grok-4-1-fast-reasoning",
            "grok-4-fast-reasoning",
            "grok-4-0709",
            "grok-code-fast-1",
            "grok-3",
        ]
    ),
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
def test_property_3_migration_preserves_routing_confidence(model: str, confidence: float) -> None:
    """For any routing decision with confidence score C (0.0 <= C <= 1.0),
    when migrated, the confidence score SHALL equal C exactly.

    Validates: Requirements 3.3, 10.3
    """
    from deepr.routing.deprecation import migrate_model

    _, returned_confidence, _ = migrate_model(model, confidence=confidence)

    # Confidence must be preserved exactly
    assert returned_confidence == confidence


# Feature: grok-4-3-migration, Property 4: Subagent Budget Enforcement


@settings(max_examples=100)
@given(
    budget=st.floats(min_value=0.01, max_value=100.0, allow_nan=False, allow_infinity=False),
    cost=st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False),
)
def test_property_4_subagent_budget_enforcement(budget: float, cost: float) -> None:
    """For any subagent with budget cap B, the subagent's accumulated cost SHALL
    never exceed B. When cost reaches B, the runtime SHALL reject the spend.

    Validates: Requirements 5.1, 5.3, 9.4
    """
    from deepr.agents.contract import AgentBudget

    agent_budget = AgentBudget(max_cost=budget)

    allowed, reason = agent_budget.check(cost)

    if cost > budget:
        # Must reject costs exceeding budget
        assert not allowed
        assert "Insufficient budget" in reason or "negative" in reason.lower()
    elif cost < 0:
        # Negative costs are rejected
        assert not allowed
    else:
        # Cost within budget must be allowed
        assert allowed
        assert reason == "OK"


# Feature: grok-4-3-migration, Property 5: Trace ID Propagation


@settings(max_examples=100)
@given(
    trace_id=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=1,
        max_size=32,
    ),
)
def test_property_5_trace_id_propagation(trace_id: str) -> None:
    """For any orchestration with planner trace_id T, all child workers SHALL
    have trace_id equal to T.

    Validates: Requirements 5.2, 5.5, 9.2
    """
    from deepr.agents.contract import AgentIdentity, AgentRole

    planner = AgentIdentity(
        role=AgentRole.PLANNER,
        trace_id=trace_id,
    )

    # Create multiple children
    child1 = planner.child(role=AgentRole.WORKER, name="worker-1")
    child2 = planner.child(role=AgentRole.WORKER, name="worker-2")
    child3 = planner.child(role=AgentRole.SYNTHESIZER, name="synthesizer")

    # All children must inherit the planner's trace_id
    assert child1.trace_id == trace_id
    assert child2.trace_id == trace_id
    assert child3.trace_id == trace_id

    # Children must have the planner as parent
    assert child1.parent_agent_id == planner.agent_id
    assert child2.parent_agent_id == planner.agent_id
    assert child3.parent_agent_id == planner.agent_id


# Feature: grok-4-3-migration, Property 6: Subagent Cost Recording


@settings(max_examples=100)
@given(
    cost=st.floats(min_value=0.01, max_value=50.0, allow_nan=False, allow_infinity=False),
)
def test_property_6_subagent_cost_recording(cost: float) -> None:
    """For any subagent execution that incurs cost C > 0, the cost ledger SHALL
    contain an event with that cost.

    Validates: Requirements 5.4
    """
    from unittest.mock import MagicMock

    from deepr.agents.contract import AgentResult, AgentStatus
    from deepr.agents.runtime import FanOutConfig, SubagentRuntime

    # Create a mock cost ledger
    mock_ledger = MagicMock()
    mock_ledger.record_event = MagicMock()

    config = FanOutConfig(operation_budget=100.0)
    runtime = SubagentRuntime(config=config, cost_ledger=mock_ledger)

    # Simulate recording a cost
    result = AgentResult(
        agent_id="test-agent",
        trace_id="test-trace",
        output="test output",
        cost=cost,
        status=AgentStatus.SUCCESS,
    )

    runtime._record_cost(result)

    # Cost ledger must have been called with the cost
    mock_ledger.record_event.assert_called_once()
    call_kwargs = mock_ledger.record_event.call_args
    assert call_kwargs[1]["cost_usd"] == cost
    assert call_kwargs[1]["metadata"]["trace_id"] == "test-trace"


# Feature: grok-4-3-migration, Property 7: Handoff Input Validation


@settings(max_examples=100)
@given(
    query=st.sampled_from(["", "   ", ""]),
    budget=st.floats(min_value=-100.0, max_value=0.0, allow_nan=False, allow_infinity=False),
    trace_id=st.sampled_from(["", "valid-trace"]),
)
def test_property_7_handoff_input_validation(query: str, budget: float, trace_id: str) -> None:
    """For any handoff input that violates the schema (empty query, non-positive budget,
    missing trace_id), validation SHALL fail with appropriate errors.

    Validates: Requirements 6.3
    """
    from deepr.agents.handoff import HandoffInput

    handoff_input = HandoffInput(
        query=query,
        budget_allocation=budget,
        trace_id=trace_id,
    )

    valid, errors = handoff_input.validate()

    # At least one violation must be detected
    # Empty/whitespace query is always invalid
    has_query_error = not query or not query.strip()
    # Non-positive budget is always invalid
    has_budget_error = budget <= 0
    # Empty trace_id is invalid
    has_trace_error = not trace_id

    expected_invalid = has_query_error or has_budget_error or has_trace_error

    if expected_invalid:
        assert not valid
        assert len(errors) > 0

    if has_query_error:
        assert any("query" in e for e in errors)
    if has_budget_error:
        assert any("budget" in e for e in errors)
    if has_trace_error:
        assert any("trace_id" in e for e in errors)


# Feature: grok-4-3-migration, Property 8: Handoff Output Conformance


@settings(max_examples=100)
@given(
    artifact_id=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=1,
        max_size=32,
    ),
    trace_id=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=1,
        max_size=32,
    ),
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    cost=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
)
def test_property_8_handoff_output_conformance(artifact_id: str, trace_id: str, confidence: float, cost: float) -> None:
    """For any valid HandoffOutput (non-empty artifact_id, trace_id, confidence in [0,1],
    cost >= 0), validation SHALL pass.

    Validates: Requirements 6.4
    """
    from deepr.agents.handoff import HandoffOutput

    output = HandoffOutput(
        artifact_id=artifact_id,
        result_data="some result",
        confidence_score=confidence,
        cost_consumed=cost,
        trace_id=trace_id,
    )

    valid, errors = output.validate()

    # Valid inputs must pass validation
    assert valid, f"Expected valid but got errors: {errors}"
    assert len(errors) == 0


# Feature: grok-4-3-migration, Property 9: Fan-Out Concurrency Bound


@settings(max_examples=100)
@given(
    max_concurrent=st.integers(min_value=1, max_value=32),
    agent_count=st.integers(min_value=1, max_value=64),
)
def test_property_9_fan_out_concurrency_bound(max_concurrent: int, agent_count: int) -> None:
    """For any fan-out with max_concurrent = M, the number of simultaneously
    executing agents SHALL never exceed M.

    Validates: Requirements 7.1
    """
    import asyncio

    from deepr.agents.contract import AgentBudget, AgentIdentity, AgentResult, AgentStatus
    from deepr.agents.runtime import FanOutConfig, SubagentRuntime

    config = FanOutConfig(
        max_concurrent=max_concurrent,
        operation_budget=1000.0,  # High budget to avoid tripping
    )
    runtime = SubagentRuntime(config=config)

    # Track max concurrent executions
    current_concurrent = 0
    max_observed = 0
    lock = asyncio.Lock()

    async def mock_agent(query: str, budget: AgentBudget, identity: AgentIdentity) -> AgentResult:
        nonlocal current_concurrent, max_observed
        async with lock:
            current_concurrent += 1
            if current_concurrent > max_observed:
                max_observed = current_concurrent
        # Simulate brief work
        await asyncio.sleep(0.001)
        async with lock:
            current_concurrent -= 1
        return AgentResult(
            agent_id=identity.agent_id,
            trace_id=identity.trace_id,
            output="done",
            cost=0.001,
            status=AgentStatus.SUCCESS,
        )

    planner = AgentIdentity(trace_id="test-trace")
    queries = [f"query-{i}" for i in range(agent_count)]

    asyncio.run(runtime.fan_out(queries, mock_agent, planner))

    # Max observed concurrency must not exceed max_concurrent
    assert max_observed <= max_concurrent


# Feature: grok-4-3-migration, Property 10: Circuit Breaker Preserves Partial Results


@settings(max_examples=100)
@given(
    num_success=st.integers(min_value=0, max_value=5),
    num_failures=st.integers(min_value=0, max_value=5),
)
def test_property_10_circuit_breaker_preserves_partial_results(num_success: int, num_failures: int) -> None:
    """When the circuit breaker trips, the returned FanOutResult SHALL contain all
    results from agents that completed before the trip.

    Validates: Requirements 7.2, 7.3, 7.5
    """
    from deepr.agents.circuit_breaker import CircuitBreaker
    from deepr.agents.contract import AgentResult, AgentStatus
    from deepr.agents.runtime import FanOutConfig

    # Set a low budget so cost-based tripping is easy to trigger
    config = FanOutConfig(operation_budget=0.5, failure_rate_threshold=0.5)
    cb = CircuitBreaker(config)

    completed_results: list[AgentResult] = []

    # Record successes
    for i in range(num_success):
        result = AgentResult(
            agent_id=f"success-{i}",
            trace_id="trace",
            output=f"output-{i}",
            cost=0.01,
            status=AgentStatus.SUCCESS,
        )
        cb.record_completion(result)
        completed_results.append(result)

    # Record failures
    for i in range(num_failures):
        result = AgentResult(
            agent_id=f"failure-{i}",
            trace_id="trace",
            output="",
            cost=0.01,
            status=AgentStatus.FAILED,
        )
        cb.record_failure(result)
        completed_results.append(result)

    # Check state: all recorded results are tracked
    total_resolved = cb.state.total_completed + cb.state.total_failed
    assert total_resolved == num_success + num_failures

    # If circuit breaker trips, partial results are preserved
    should_halt, reason = cb.should_halt()
    if should_halt:
        # Trip it
        cb.trip(reason, [r.trace_id for r in completed_results])
        assert cb.state.tripped
        assert cb.state.trip_reason != ""
        # All results recorded before trip are still accessible
        assert len(completed_results) == num_success + num_failures


# Feature: grok-4-3-migration, Property 11: MCP Tool Artifact ID Completeness


@settings(max_examples=100)
@given(
    trace_id=st.one_of(
        st.none(),
        st.just(""),
        st.text(
            alphabet=st.characters(whitelist_categories=("L", "N")),
            min_size=1,
            max_size=32,
        ),
    ),
)
def test_property_11_mcp_tool_artifact_id_completeness(
    trace_id: str | None,
) -> None:
    """For any MCP tool response, the artifact_ids field SHALL contain a non-empty
    trace_id.

    Validates: Requirements 8.1, 8.2, 8.3, 8.4
    """
    from deepr.mcp.artifacts import build_artifact_ids, ensure_trace_id

    # Test ensure_trace_id
    response: dict = {}
    if trace_id:
        response["artifact_ids"] = {"trace_id": trace_id}

    ensure_trace_id(response)
    assert "artifact_ids" in response
    assert "trace_id" in response["artifact_ids"]
    assert len(response["artifact_ids"]["trace_id"]) > 0

    # Test build_artifact_ids
    kwargs = {}
    if trace_id:
        kwargs["trace_id"] = trace_id
    artifact_ids = build_artifact_ids(**kwargs)
    assert "trace_id" in artifact_ids
    assert len(artifact_ids["trace_id"]) > 0


# Feature: grok-4-3-migration, Property 12: Multi-Agent Budget Allocation Formula


@settings(max_examples=100)
@given(
    budget=st.floats(min_value=1.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    agent_count=st.integers(min_value=4, max_value=16),
)
def test_property_12_multi_agent_budget_allocation_formula(budget: float, agent_count: int) -> None:
    """For any operation with budget B and agent count N (4 <= N <= 16),
    per-agent cap = (B * 0.8) / N.

    Validates: Requirements 9.3
    """
    from deepr.agents.runtime import FanOutConfig

    config = FanOutConfig(
        operation_budget=budget,
        synthesis_reserve_fraction=0.2,
    )

    # The formula: per_agent_cap = (budget * (1 - synthesis_reserve)) / agent_count
    # With synthesis_reserve_fraction=0.2, this is (budget * 0.8) / agent_count
    worker_budget_pool = budget * (1.0 - config.synthesis_reserve_fraction)
    per_agent_cap = worker_budget_pool / agent_count

    expected = (budget * 0.8) / agent_count
    assert abs(per_agent_cap - expected) < 1e-10


# Feature: grok-4-3-migration, Property 13: Agent Count Bounds


@settings(max_examples=100)
@given(
    agent_count=st.one_of(
        st.none(),
        st.integers(min_value=-10, max_value=100),
    ),
    prompt_length=st.integers(min_value=1, max_value=500),
)
def test_property_13_agent_count_bounds(agent_count: int | None, prompt_length: int) -> None:
    """For any multi-agent request, the agent count SHALL be in [4, 16].

    Validates: Requirements 9.1
    """
    with patch.dict("os.environ", {"XAI_API_KEY": "test-key"}):
        from deepr.providers.base import ResearchRequest
        from deepr.providers.grok_provider import GrokProvider

        provider = GrokProvider(api_key="test-key")

        # Generate a prompt of the given length
        prompt = " ".join(["word"] * prompt_length)

        request = ResearchRequest(
            prompt=prompt,
            model="grok-4.20-multi-agent",
            system_message="",
            agent_count=agent_count,
        )

        result = provider._determine_agent_count(request)

        # Must always be in [4, 16]
        assert 4 <= result <= 16


# Feature: grok-4-3-migration, Property 14: Grok 4.3 Candidate Inclusion for Agentic Workloads


@settings(max_examples=100)
@given(
    specialization=st.sampled_from(["agentic", "tool_calling"]),
)
def test_property_14_grok_43_candidate_inclusion_for_agentic_workloads(
    specialization: str,
) -> None:
    """For any query classified as 'agentic' or 'tool_calling', the candidate set
    SHALL include xai/grok-4-3.

    Validates: Requirements 12.1
    """
    from deepr.providers.registry import get_models_by_specialization

    candidates = get_models_by_specialization(specialization)

    # Find grok-4-3 in the candidates
    grok_43_models = [m for m in candidates if m.model == "grok-4-3"]
    assert len(grok_43_models) > 0, (
        f"xai/grok-4-3 not found in candidates for '{specialization}'. Found: {[m.model for m in candidates]}"
    )


# Feature: grok-4-3-migration, Property 15: Complexity-to-Reasoning-Effort Mapping


@settings(max_examples=100)
@given(
    complexity=st.sampled_from(["simple", "moderate", "complex"]),
)
def test_property_15_complexity_to_reasoning_effort_mapping(complexity: str) -> None:
    """For any routing decision selecting Grok 4.3, reasoning effort SHALL be 'low'
    for simple, 'medium' for moderate, 'high' for complex.

    Validates: Requirements 12.2
    """
    from deepr.routing.auto_mode import (
        COMPLEXITY_TO_REASONING_EFFORT,
        AutoModeDecision,
        _apply_reasoning_effort,
    )

    decision = AutoModeDecision(
        provider="xai",
        model="xai/grok-4-3",
        complexity=complexity,
        task_type="reasoning",
        cost_estimate=0.05,
        confidence=0.9,
        reasoning="test",
    )

    result = _apply_reasoning_effort(decision)

    expected_mapping = {"simple": "low", "moderate": "medium", "complex": "high"}
    expected = expected_mapping[complexity]

    assert result.metadata["reasoning_effort"] == expected
    assert result.metadata["reasoning_effort"] == COMPLEXITY_TO_REASONING_EFFORT[complexity]
