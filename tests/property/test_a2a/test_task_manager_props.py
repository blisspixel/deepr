"""Property tests for TaskManager.

Feature: mcp-client-agent-interop
Properties: 17, 18
Validates: Requirements 8.3, 8.5, 8.6, 8.7
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from deepr.a2a.models import TaskRequest, TaskState
from deepr.a2a.task_manager import InvalidTransitionError, TaskManager

# --- Strategies ---

skill_st = st.sampled_from(["recon", "distillr", "primr", "analyst"])
input_st = st.text(min_size=1, max_size=50)
budget_st = st.one_of(st.none(), st.floats(min_value=0.1, max_value=100.0))
cost_st = st.floats(min_value=0.0, max_value=50.0)
trace_id_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=8,
    max_size=16,
)


# --- Property 17: Task lifecycle state machine ---


@settings(max_examples=200)
@given(
    skill=skill_st,
    input_text=input_st,
    cost=cost_st,
    trace_id=trace_id_st,
)
def test_task_lifecycle_valid_transitions(
    skill: str,
    input_text: str,
    cost: float,
    trace_id: str,
) -> None:
    """Property 17: Task lifecycle state machine.

    Valid path: submitted → working → completed with cost and trace_id.

    **Validates: Requirements 8.3, 8.5, 8.6**
    """
    manager = TaskManager()
    request = TaskRequest(skill=skill, input=input_text)

    # Create task
    task = manager.create_task(request)
    assert task.state == TaskState.SUBMITTED

    # Transition to working
    task = manager.transition(task.id, TaskState.WORKING)
    assert task.state == TaskState.WORKING

    # Transition to completed
    task = manager.transition(
        task.id,
        TaskState.COMPLETED,
        result={"data": "test"},
        cost=cost,
        trace_id=trace_id,
    )
    assert task.state == TaskState.COMPLETED
    assert task.cost == cost
    assert task.trace_id == trace_id
    assert task.result == {"data": "test"}


@settings(max_examples=200)
@given(
    skill=skill_st,
    input_text=input_st,
)
def test_task_lifecycle_failure_path(
    skill: str,
    input_text: str,
) -> None:
    """Property 17: Failed tasks contain structured error.

    Valid path: submitted → working → failed with error info.

    **Validates: Requirements 8.3, 8.6**
    """
    manager = TaskManager()
    request = TaskRequest(skill=skill, input=input_text)

    task = manager.create_task(request)
    task = manager.transition(task.id, TaskState.WORKING)
    task = manager.transition(
        task.id,
        TaskState.FAILED,
        error={"reason": "timeout", "retryable": True},
    )

    assert task.state == TaskState.FAILED
    assert task.error is not None
    assert task.error["retryable"] is True


@settings(max_examples=100)
@given(
    skill=skill_st,
    input_text=input_st,
    invalid_target=st.sampled_from([TaskState.COMPLETED, TaskState.FAILED]),
)
def test_invalid_transitions_rejected(
    skill: str,
    input_text: str,
    invalid_target: TaskState,
) -> None:
    """Property 17: Invalid transitions are rejected.

    Cannot go directly from submitted to completed/failed.

    **Validates: Requirements 8.5**
    """
    manager = TaskManager()
    request = TaskRequest(skill=skill, input=input_text)
    task = manager.create_task(request)

    try:
        manager.transition(task.id, invalid_target)
        raise AssertionError(f"Should have rejected {TaskState.SUBMITTED} → {invalid_target}")
    except InvalidTransitionError as e:
        assert e.current_state == TaskState.SUBMITTED
        assert e.target_state == invalid_target


# --- Property 18: A2A budget propagation ---


@settings(max_examples=100)
@given(
    skill=skill_st,
    input_text=input_st,
    budget=st.floats(min_value=0.1, max_value=100.0),
)
def test_budget_propagation(
    skill: str,
    input_text: str,
    budget: float,
) -> None:
    """Property 18: A2A budget propagation.

    For any task request with a budget value, the created task's metadata
    contains a budget_cap equal to the request's budget.

    **Validates: Requirements 8.7**
    """
    manager = TaskManager()
    request = TaskRequest(skill=skill, input=input_text, budget=budget)

    task = manager.create_task(request)

    assert "budget_cap" in task.metadata, "Task should have budget_cap in metadata"
    assert task.metadata["budget_cap"] == budget, f"Budget cap {task.metadata['budget_cap']} != request budget {budget}"
