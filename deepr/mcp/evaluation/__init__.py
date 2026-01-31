"""
Agent Trajectory Evaluation module.

Provides metrics tracking for evaluating agent performance:
- Trajectory efficiency (steps vs optimal path)
- Citation accuracy (beliefs with cited sources)
- Hallucination rate (invented parameters)
- Context economy (tokens per task)
"""

from .metrics import (
    TrajectoryMetrics,
    TrajectoryStep,
    MetricsTracker,
    calculate_efficiency,
    calculate_citation_accuracy,
    detect_hallucinations,
    calculate_context_economy,
)

__all__ = [
    "TrajectoryMetrics",
    "TrajectoryStep",
    "MetricsTracker",
    "calculate_efficiency",
    "calculate_citation_accuracy",
    "detect_hallucinations",
    "calculate_context_economy",
]
