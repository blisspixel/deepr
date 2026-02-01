"""MetadataEmitter for structured observability.

Provides lightweight span tracking with cost attribution for research operations.

Usage:
    emitter = MetadataEmitter()
    
    # Track a research operation
    with emitter.operation("research_job", {"query": "quantum computing"}) as op:
        # ... do work ...
        op.set_cost(0.15)
        op.add_event("search_complete", {"results": 10})
    
    # Get timeline
    timeline = emitter.get_timeline()
    
    # Save trace
    emitter.save_trace(Path("data/traces/trace_001.json"))
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from contextlib import contextmanager

from deepr.observability.traces import TraceContext, Span, SpanStatus, get_or_create_trace


@dataclass
class TaskMetadata:
    """Metadata for a research task.
    
    Attributes:
        task_id: Unique identifier for the task
        task_type: Type of task (research, chat, synthesis, etc.)
        prompt: The prompt or query
        model: Model used
        provider: Provider used
        tokens_input: Input tokens consumed
        tokens_output: Output tokens generated
        cost: Cost in dollars
        context_sources: Sources used for context
        start_time: When the task started
        end_time: When the task ended
        status: Task status
        error: Error message if failed
        parent_task_id: ID of parent task (for nested operations)
    """
    task_id: str
    task_type: str
    prompt: str = ""
    model: str = ""
    provider: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    cost: float = 0.0
    context_sources: List[str] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    status: str = "running"
    error: Optional[str] = None
    parent_task_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "prompt": self.prompt,
            "model": self.model,
            "provider": self.provider,
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "cost": self.cost,
            "context_sources": self.context_sources,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "status": self.status,
            "error": self.error,
            "parent_task_id": self.parent_task_id,
            "duration_ms": self.duration_ms
        }
    
    @property
    def duration_ms(self) -> Optional[float]:
        """Get task duration in milliseconds."""
        if self.end_time is None:
            return None
        delta = self.end_time - self.start_time
        return delta.total_seconds() * 1000


class OperationContext:
    """Context for an operation being tracked.
    
    Provides a fluent interface for setting metadata during an operation.
    """
    
    def __init__(self, span: Span, metadata: TaskMetadata, emitter: "MetadataEmitter"):
        self.span = span
        self.metadata = metadata
        self._emitter = emitter
    
    def set_cost(self, cost: float):
        """Set the cost for this operation.
        
        Args:
            cost: Cost in dollars
        """
        self.span.set_cost(cost)
        self.metadata.cost = cost
    
    def set_tokens(self, input_tokens: int, output_tokens: int):
        """Set token counts for this operation.
        
        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
        """
        self.metadata.tokens_input = input_tokens
        self.metadata.tokens_output = output_tokens
        self.span.set_attribute("tokens_input", input_tokens)
        self.span.set_attribute("tokens_output", output_tokens)
    
    def set_model(self, model: str, provider: str = ""):
        """Set the model used for this operation.
        
        Args:
            model: Model name
            provider: Provider name
        """
        self.metadata.model = model
        self.metadata.provider = provider
        self.span.set_attribute("model", model)
        self.span.set_attribute("provider", provider)
    
    def add_context_source(self, source: str):
        """Add a context source used in this operation.
        
        Args:
            source: Source identifier (filename, URL, etc.)
        """
        self.metadata.context_sources.append(source)
        self.span.set_attribute("context_sources", self.metadata.context_sources)
    
    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        """Add a timestamped event to this operation.
        
        Args:
            name: Event name
            attributes: Optional event attributes
        """
        self.span.add_event(name, attributes)
    
    def set_attribute(self, key: str, value: Any):
        """Set a custom attribute on this operation.
        
        Args:
            key: Attribute name
            value: Attribute value
        """
        self.span.set_attribute(key, value)


class MetadataEmitter:
    """Emitter for structured task metadata with span tracking.
    
    Provides:
    - Lightweight span tracking (start_span, end_span)
    - Parent-child relationship tracking
    - Cost attribution per span
    - Timeline generation
    - Trace persistence
    
    Attributes:
        trace_context: The underlying trace context
        tasks: List of task metadata
    """
    
    def __init__(self, trace_context: Optional[TraceContext] = None):
        """Initialize MetadataEmitter.
        
        Args:
            trace_context: Optional existing trace context
        """
        self.trace_context = trace_context or get_or_create_trace()
        self.tasks: List[TaskMetadata] = []
        self._active_operations: Dict[str, OperationContext] = {}
    
    def start_task(
        self,
        task_type: str,
        prompt: str = "",
        attributes: Optional[Dict[str, Any]] = None
    ) -> OperationContext:
        """Start tracking a new task.
        
        Args:
            task_type: Type of task (research, chat, synthesis, etc.)
            prompt: The prompt or query
            attributes: Optional initial attributes
            
        Returns:
            OperationContext for the task
        """
        # Start span
        span = self.trace_context.start_span(task_type, attributes)
        span.set_attribute("prompt", prompt[:500] if prompt else "")  # Truncate long prompts
        
        # Create metadata
        metadata = TaskMetadata(
            task_id=span.span_id,
            task_type=task_type,
            prompt=prompt,
            parent_task_id=span.parent_span_id
        )
        self.tasks.append(metadata)
        
        # Create operation context
        op = OperationContext(span, metadata, self)
        self._active_operations[span.span_id] = op
        
        return op
    
    def complete_task(self, op: OperationContext, status: str = "completed"):
        """Mark a task as complete.
        
        Args:
            op: The operation context
            status: Final status
        """
        op.metadata.end_time = datetime.utcnow()
        op.metadata.status = status
        
        span_status = SpanStatus.COMPLETED if status == "completed" else SpanStatus.FAILED
        self.trace_context.end_span(op.span, span_status)
        
        # Remove from active operations
        self._active_operations.pop(op.span.span_id, None)
    
    def fail_task(self, op: OperationContext, error: str):
        """Mark a task as failed.
        
        Args:
            op: The operation context
            error: Error message
        """
        op.metadata.end_time = datetime.utcnow()
        op.metadata.status = "failed"
        op.metadata.error = error
        
        op.span.fail(error)
        
        # Remove from active operations
        self._active_operations.pop(op.span.span_id, None)
    
    @contextmanager
    def operation(
        self,
        task_type: str,
        attributes: Optional[Dict[str, Any]] = None,
        prompt: str = ""
    ):
        """Context manager for tracking an operation.
        
        Args:
            task_type: Type of task
            attributes: Optional initial attributes
            prompt: The prompt or query
            
        Yields:
            OperationContext for the operation
        """
        op = self.start_task(task_type, prompt, attributes)
        try:
            yield op
            self.complete_task(op)
        except Exception as e:
            self.fail_task(op, str(e))
            raise
    
    def get_timeline(self) -> List[Dict[str, Any]]:
        """Get a timeline of all tasks.
        
        Returns:
            List of task dictionaries sorted by start time
        """
        timeline = []
        for task in sorted(self.tasks, key=lambda t: t.start_time):
            entry = task.to_dict()
            
            # Add hierarchy info
            if task.parent_task_id:
                parent = next(
                    (t for t in self.tasks if t.task_id == task.parent_task_id),
                    None
                )
                if parent:
                    entry["parent_type"] = parent.task_type
            
            timeline.append(entry)
        
        return timeline
    
    def get_cost_breakdown(self) -> Dict[str, float]:
        """Get cost breakdown by task type.
        
        Returns:
            Dictionary mapping task type to total cost
        """
        breakdown: Dict[str, float] = {}
        for task in self.tasks:
            if task.task_type not in breakdown:
                breakdown[task.task_type] = 0.0
            breakdown[task.task_type] += task.cost
        return breakdown
    
    def get_total_cost(self) -> float:
        """Get total cost across all tasks.
        
        Returns:
            Total cost in dollars
        """
        return sum(t.cost for t in self.tasks)
    
    def get_context_lineage(self) -> Dict[str, List[str]]:
        """Get context lineage showing which sources were used by which tasks.
        
        Returns:
            Dictionary mapping task_id to list of context sources
        """
        return {
            task.task_id: task.context_sources
            for task in self.tasks
            if task.context_sources
        }
    
    def save_trace(self, path: Path):
        """Save the complete trace to a JSON file.
        
        Args:
            path: Path to save to
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        
        trace_data = {
            "trace_id": self.trace_context.trace_id,
            "tasks": [t.to_dict() for t in self.tasks],
            "spans": [s.to_dict() for s in self.trace_context.spans],
            "timeline": self.get_timeline(),
            "cost_breakdown": self.get_cost_breakdown(),
            "total_cost": self.get_total_cost(),
            "context_lineage": self.get_context_lineage(),
            "exported_at": datetime.utcnow().isoformat()
        }
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(trace_data, f, indent=2)
    
    @classmethod
    def load_trace(cls, path: Path) -> "MetadataEmitter":
        """Load a trace from a JSON file.
        
        Args:
            path: Path to load from
            
        Returns:
            MetadataEmitter instance
        """
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Load trace context
        trace_context = TraceContext(trace_id=data.get("trace_id"))
        
        # Load spans
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
            trace_context.spans.append(span)
        
        # Create emitter
        emitter = cls(trace_context)
        
        # Load tasks
        for task_data in data.get("tasks", []):
            task = TaskMetadata(
                task_id=task_data["task_id"],
                task_type=task_data["task_type"],
                prompt=task_data.get("prompt", ""),
                model=task_data.get("model", ""),
                provider=task_data.get("provider", ""),
                tokens_input=task_data.get("tokens_input", 0),
                tokens_output=task_data.get("tokens_output", 0),
                cost=task_data.get("cost", 0.0),
                context_sources=task_data.get("context_sources", []),
                start_time=datetime.fromisoformat(task_data["start_time"]),
                end_time=datetime.fromisoformat(task_data["end_time"]) if task_data.get("end_time") else None,
                status=task_data.get("status", "completed"),
                error=task_data.get("error"),
                parent_task_id=task_data.get("parent_task_id")
            )
            emitter.tasks.append(task)
        
        return emitter
