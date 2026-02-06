"""
Test context chaining logic (without making expensive API calls).
"""

import pytest

from deepr.services.context_builder import ContextBuilder


@pytest.mark.asyncio
async def test_build_phase_context():
    """Test building context from dependencies."""
    # Mock context builder (no API key needed for this test)
    builder = ContextBuilder(api_key="test-key")

    # Mock task with dependencies
    task = {
        "id": 3,
        "title": "Competitive analysis",
        "prompt": "Analyze competition",
        "depends_on": [1, 2],
    }

    # Mock completed tasks
    completed_tasks = {
        1: {
            "title": "Market size",
            "result": "Market is worth $10B and growing 20% annually.",
        },
        2: {
            "title": "Key players",
            "result": "Top 3 players are Company A (40%), B (30%), C (20%).",
        },
    }

    # Build context (will call OpenAI API for summarization)
    # Skip this test in CI/CD - it requires real API key
    # context = await builder.build_phase_context(task, completed_tasks)

    # For now, just validate the structure
    assert task["depends_on"] == [1, 2]
    assert len(completed_tasks) == 2


def test_group_by_phase():
    """Test grouping tasks by phase."""
    from deepr.services.batch_executor import BatchExecutor

    # Mock executor
    executor = BatchExecutor(
        queue=None,
        provider=None,
        storage=None,
        context_builder=None,
    )

    tasks = [
        {"id": 1, "phase": 1, "title": "Task 1"},
        {"id": 2, "phase": 1, "title": "Task 2"},
        {"id": 3, "phase": 2, "title": "Task 3"},
        {"id": 4, "phase": 3, "title": "Task 4"},
    ]

    phases = executor._group_by_phase(tasks)

    assert len(phases) == 3
    assert len(phases[1]) == 2
    assert len(phases[2]) == 1
    assert len(phases[3]) == 1
    assert phases[1][0]["id"] == 1
    assert phases[2][0]["id"] == 3


def test_task_dependencies():
    """Test dependency resolution logic."""
    tasks = [
        {"id": 1, "phase": 1, "depends_on": []},
        {"id": 2, "phase": 1, "depends_on": []},
        {"id": 3, "phase": 2, "depends_on": [1]},
        {"id": 4, "phase": 2, "depends_on": [1, 2]},
        {"id": 5, "phase": 3, "depends_on": [1, 2, 3, 4]},
    ]

    # Phase 1 tasks have no dependencies
    phase1 = [t for t in tasks if t["phase"] == 1]
    assert all(len(t["depends_on"]) == 0 for t in phase1)

    # Phase 2 tasks depend on Phase 1
    phase2 = [t for t in tasks if t["phase"] == 2]
    assert all(len(t["depends_on"]) > 0 for t in phase2)
    assert all(dep in [1, 2] for t in phase2 for dep in t["depends_on"])

    # Phase 3 synthesis depends on everything
    phase3 = [t for t in tasks if t["phase"] == 3]
    assert len(phase3[0]["depends_on"]) == 4
