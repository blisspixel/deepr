"""Canonical trace model for Deepr observability.

Provides distributed tracing primitives for tracking research operations:
- TraceContext: Propagates trace_id and span_id through operations
- Span: Represents a unit of work with timing and metadata
- SpanStatus: Status of a span (running, completed, failed)

Usage:
    # Create a trace context
    ctx = TraceContext.create()
    
    # Start a span
    with ctx.span("research_job") as span:
        span.set_attribute("query", "quantum computing")
        # ... do work ...
        span.set_attribute("cost", 0.15)
    
    # Nested spans
    with ctx.span("parent_operation") as parent:
        with ctx.span("child_operation") as child:
            # child automatically has parent_span_id set
            pass
"""

import uuid
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)
from typing import Optional, Dict, Any, List
from pathlib import Path
from contextlib import contextmanager
import threading


class SpanStatus(Enum):
    """Status of a span."""
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Span:
    """A span represents a unit of work within a trace.
    
    Attributes:
        span_id: Unique identifier for this span
        trace_id: Identifier for the overall trace
        parent_span_id: ID of parent span (None for root spans)
        name: Human-readable name of the operation
        start_time: When the span started
        end_time: When the span ended (None if still running)
        status: Current status of the span
        attributes: Key-value metadata about the operation
        events: List of timestamped events during the span
        cost: Cost attributed to this span (for cost tracking)
    """
    span_id: str
    trace_id: str
    parent_span_id: Optional[str]
    name: str
    start_time: datetime = field(default_factory=_utc_now)
    end_time: Optional[datetime] = None
    status: SpanStatus = SpanStatus.RUNNING
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    cost: float = 0.0
    
    def set_attribute(self, key: str, value: Any):
        """Set an attribute on the span.
        
        Args:
            key: Attribute name
            value: Attribute value (must be JSON-serializable)
        """
        self.attributes[key] = value
    
    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        """Add a timestamped event to the span.
        
        Args:
            name: Event name
            attributes: Optional event attributes
        """
        self.events.append({
            "name": name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "attributes": attributes or {}
        })
    
    def set_cost(self, cost: float):
        """Set the cost attributed to this span.
        
        Args:
            cost: Cost in dollars
        """
        self.cost = cost
    
    def complete(self, status: SpanStatus = SpanStatus.COMPLETED):
        """Mark the span as complete.
        
        Args:
            status: Final status (default: COMPLETED)
        """
        self.end_time = datetime.now(timezone.utc)
        self.status = status
    
    def fail(self, error: Optional[str] = None):
        """Mark the span as failed.
        
        Args:
            error: Optional error message
        """
        self.end_time = datetime.now(timezone.utc)
        self.status = SpanStatus.FAILED
        if error:
            self.set_attribute("error", error)
    
    @property
    def duration_ms(self) -> Optional[float]:
        """Get span duration in milliseconds."""
        if self.end_time is None:
            return None
        delta = self.end_time - self.start_time
        return delta.total_seconds() * 1000
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert span to dictionary for serialization."""
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "attributes": self.attributes,
            "events": self.events,
            "cost": self.cost
        }


class TraceContext:
    """Context for distributed tracing.
    
    Manages trace_id and span_id propagation through nested operations.
    Thread-safe for concurrent operations.
    
    Attributes:
        trace_id: Unique identifier for the entire trace
        spans: List of all spans in this trace
        current_span_id: ID of the currently active span
    """
    
    # Thread-local storage for current context
    _local = threading.local()
    
    def __init__(self, trace_id: Optional[str] = None):
        """Initialize trace context.
        
        Args:
            trace_id: Optional trace ID (generated if not provided)
        """
        self.trace_id = trace_id or str(uuid.uuid4())
        self.spans: List[Span] = []
        self._span_stack: List[str] = []  # Stack of active span IDs
        self._lock = threading.Lock()
    
    @classmethod
    def create(cls) -> "TraceContext":
        """Create a new trace context.
        
        Returns:
            New TraceContext instance
        """
        ctx = cls()
        cls._local.current = ctx
        return ctx
    
    @classmethod
    def get_current(cls) -> Optional["TraceContext"]:
        """Get the current trace context.
        
        Returns:
            Current TraceContext or None
        """
        return getattr(cls._local, "current", None)
    
    @property
    def current_span_id(self) -> Optional[str]:
        """Get the ID of the currently active span."""
        with self._lock:
            return self._span_stack[-1] if self._span_stack else None
    
    def start_span(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> Span:
        """Start a new span.
        
        Args:
            name: Name of the operation
            attributes: Optional initial attributes
            
        Returns:
            The new Span
        """
        span_id = str(uuid.uuid4())
        
        with self._lock:
            parent_span_id = self._span_stack[-1] if self._span_stack else None
            
            span = Span(
                span_id=span_id,
                trace_id=self.trace_id,
                parent_span_id=parent_span_id,
                name=name,
                attributes=attributes or {}
            )
            
            self.spans.append(span)
            self._span_stack.append(span_id)
        
        return span
    
    def end_span(self, span: Span, status: SpanStatus = SpanStatus.COMPLETED):
        """End a span.
        
        Args:
            span: The span to end
            status: Final status
        """
        span.complete(status)
        
        with self._lock:
            if self._span_stack and self._span_stack[-1] == span.span_id:
                self._span_stack.pop()
    
    @contextmanager
    def span(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        """Context manager for creating spans.
        
        Args:
            name: Name of the operation
            attributes: Optional initial attributes
            
        Yields:
            The Span object
        """
        span = self.start_span(name, attributes)
        try:
            yield span
            self.end_span(span, SpanStatus.COMPLETED)
        except Exception as e:
            span.fail(str(e))
            with self._lock:
                if self._span_stack and self._span_stack[-1] == span.span_id:
                    self._span_stack.pop()
            raise
    
    def get_span(self, span_id: str) -> Optional[Span]:
        """Get a span by ID.
        
        Args:
            span_id: The span ID
            
        Returns:
            The Span or None
        """
        for span in self.spans:
            if span.span_id == span_id:
                return span
        return None
    
    def get_root_spans(self) -> List[Span]:
        """Get all root spans (spans without parents).
        
        Returns:
            List of root spans
        """
        return [s for s in self.spans if s.parent_span_id is None]
    
    def get_children(self, span_id: str) -> List[Span]:
        """Get child spans of a given span.
        
        Args:
            span_id: Parent span ID
            
        Returns:
            List of child spans
        """
        return [s for s in self.spans if s.parent_span_id == span_id]
    
    def get_total_cost(self) -> float:
        """Get total cost across all spans.
        
        Returns:
            Total cost in dollars
        """
        return sum(s.cost for s in self.spans)
    
    def get_total_duration_ms(self) -> Optional[float]:
        """Get total duration from first span start to last span end.
        
        Returns:
            Duration in milliseconds or None if no completed spans
        """
        if not self.spans:
            return None
        
        start = min(s.start_time for s in self.spans)
        completed = [s for s in self.spans if s.end_time is not None]
        
        if not completed:
            return None
        
        end = max(s.end_time for s in completed)
        delta = end - start
        return delta.total_seconds() * 1000
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert trace to dictionary for serialization."""
        return {
            "trace_id": self.trace_id,
            "spans": [s.to_dict() for s in self.spans],
            "total_cost": self.get_total_cost(),
            "total_duration_ms": self.get_total_duration_ms()
        }
    
    def save(self, path: Path):
        """Save trace to JSON file.
        
        Args:
            path: Path to save to
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def load(cls, path: Path) -> "TraceContext":
        """Load trace from JSON file.
        
        Args:
            path: Path to load from
            
        Returns:
            TraceContext instance
        """
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        ctx = cls(trace_id=data["trace_id"])
        
        for span_data in data.get("spans", []):
            span = Span(
                span_id=span_data["span_id"],
                trace_id=span_data["trace_id"],
                parent_span_id=span_data.get("parent_span_id"),
                name=span_data["name"],
                start_time=datetime.fromisoformat(span_data["start_time"]),
                end_time=datetime.fromisoformat(span_data["end_time"]) if span_data.get("end_time") else None,
                status=SpanStatus(span_data.get("status", "completed")),
                attributes=span_data.get("attributes", {}),
                events=span_data.get("events", []),
                cost=span_data.get("cost", 0.0)
            )
            ctx.spans.append(span)
        
        return ctx


# Convenience function for getting/creating trace context
def get_or_create_trace() -> TraceContext:
    """Get current trace context or create a new one.
    
    Returns:
        TraceContext instance
    """
    ctx = TraceContext.get_current()
    if ctx is None:
        ctx = TraceContext.create()
    return ctx
