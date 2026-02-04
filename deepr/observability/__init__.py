"""Observability module for Deepr.

Provides tracing, metrics, and cost tracking for research operations.
"""

from deepr.observability.traces import TraceContext, Span, SpanStatus, get_or_create_trace
from deepr.observability.metadata import MetadataEmitter, TaskMetadata, OperationContext
from deepr.observability.quality_metrics import QualityMetrics, EvaluationResult, MetricsSummary
from deepr.observability.stopping_criteria import (
    EntropyStoppingCriteria,
    Finding,
    PhaseContext,
    StoppingDecision,
)
from deepr.observability.information_gain import (
    InformationGainTracker,
    InformationGainMetrics,
    PriorContext,
)
from deepr.observability.temporal_tracker import (
    TemporalKnowledgeTracker,
    TemporalFinding,
    Hypothesis,
    HypothesisEvolution,
    FindingType,
    EvolutionType,
)
from deepr.observability.timeline_renderer import TimelineRenderer

__all__ = [
    "TraceContext",
    "Span",
    "SpanStatus",
    "get_or_create_trace",
    "MetadataEmitter",
    "TaskMetadata",
    "OperationContext",
    "QualityMetrics",
    "EvaluationResult",
    "MetricsSummary",
    # Stopping criteria
    "EntropyStoppingCriteria",
    "Finding",
    "PhaseContext",
    "StoppingDecision",
    # Information gain
    "InformationGainTracker",
    "InformationGainMetrics",
    "PriorContext",
    # Temporal tracking
    "TemporalKnowledgeTracker",
    "TemporalFinding",
    "Hypothesis",
    "HypothesisEvolution",
    "FindingType",
    "EvolutionType",
    "TimelineRenderer",
]
