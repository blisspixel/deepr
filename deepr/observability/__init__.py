"""Observability module for Deepr.

Provides tracing, metrics, and cost tracking for research operations.
"""

from deepr.observability.information_gain import (
    InformationGainMetrics,
    InformationGainTracker,
    PriorContext,
)
from deepr.observability.metadata import MetadataEmitter, OperationContext, TaskMetadata
from deepr.observability.quality_metrics import EvaluationResult, MetricsSummary, QualityMetrics
from deepr.observability.stopping_criteria import (
    EntropyStoppingCriteria,
    Finding,
    PhaseContext,
    StoppingDecision,
)
from deepr.observability.temporal_tracker import (
    EvolutionType,
    FindingType,
    Hypothesis,
    HypothesisEvolution,
    TemporalFinding,
    TemporalKnowledgeTracker,
)
from deepr.observability.timeline_renderer import TimelineRenderer
from deepr.observability.traces import Span, SpanStatus, TraceContext, get_or_create_trace

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
