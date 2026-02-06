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
    # Stopping criteria
    "EntropyStoppingCriteria",
    "EvaluationResult",
    "EvolutionType",
    "Finding",
    "FindingType",
    "Hypothesis",
    "HypothesisEvolution",
    "InformationGainMetrics",
    # Information gain
    "InformationGainTracker",
    "MetadataEmitter",
    "MetricsSummary",
    "OperationContext",
    "PhaseContext",
    "PriorContext",
    "QualityMetrics",
    "Span",
    "SpanStatus",
    "StoppingDecision",
    "TaskMetadata",
    "TemporalFinding",
    # Temporal tracking
    "TemporalKnowledgeTracker",
    "TimelineRenderer",
    "TraceContext",
    "get_or_create_trace",
]
