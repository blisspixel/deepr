"""Smart query routing for cost-effective research.

This package provides intelligent routing of queries to optimal models
based on complexity, task type, and cost considerations.

Auto mode enables processing 20+ queries for $1-2 instead of $20-40 by
routing simple queries to fast/cheap models while reserving expensive
deep research models for complex queries.

Usage:
    from deepr.routing import AutoModeRouter, AutoModeDecision

    router = AutoModeRouter()
    decision = router.route("What is Python?")
    # → grok-4-fast ($0.01)

    decision = router.route("Analyze Tesla's competitive position")
    # → o3-deep-research ($0.50)
"""

from deepr.routing.auto_mode import AutoModeDecision, AutoModeRouter

__all__ = ["AutoModeRouter", "AutoModeDecision"]
