"""
Agent Trajectory Evaluation module.

Provides metrics tracking for evaluating agent performance:
- Trajectory efficiency (steps vs optimal path)
- Citation accuracy (beliefs with cited sources)
- Hallucination rate (invented parameters)
- Context economy (tokens per task)
"""

from .metrics import (
    MetricsTracker,
    TrajectoryMetrics,
    TrajectoryStep,
    calculate_citation_accuracy,
    calculate_context_economy,
    calculate_efficiency,
    detect_hallucinations,
)

__all__ = [
    "MetricsTracker",
    "TrajectoryMetrics",
    "TrajectoryStep",
    "calculate_citation_accuracy",
    "calculate_context_economy",
    "calculate_efficiency",
    "detect_hallucinations",
]
