"""Observability module for Deepr.

Provides tracing, metrics, and cost tracking for research operations.
"""

from deepr.observability.traces import TraceContext, Span, SpanStatus, get_or_create_trace
from deepr.observability.metadata import MetadataEmitter, TaskMetadata, OperationContext
from deepr.observability.quality_metrics import QualityMetrics, EvaluationResult, MetricsSummary

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
    "MetricsSummary"
]
