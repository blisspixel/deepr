"""Handoff contracts for expert interoperability.

Defines structured input/output specifications for expert handoffs,
enabling upstream agents to pass work to experts and receive
standardized artifacts for downstream consumers.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class HandoffInput:
    """Structured input for expert handoffs.

    Defines what data an expert receives from upstream agents including
    the query, context references, budget allocation, and tracing info.
    """

    query: str
    context_references: list[str] = field(default_factory=list)
    budget_allocation: float = 1.0
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    expected_output_format: str = "markdown"
    metadata: dict[str, Any] = field(default_factory=dict)

    REQUIRED_FIELDS = {"query", "trace_id", "budget_allocation"}

    def validate(self) -> tuple[bool, list[str]]:
        """Validate input against schema.

        Returns:
            (valid, errors) tuple where valid is True if no errors found.
        """
        errors: list[str] = []
        if not self.query or not self.query.strip():
            errors.append("query must be non-empty")
        if self.budget_allocation <= 0:
            errors.append("budget_allocation must be positive")
        if not self.trace_id:
            errors.append("trace_id is required")
        return len(errors) == 0, errors


@dataclass
class HandoffOutput:
    """Structured output from expert handoffs.

    Defines what artifacts an expert produces for downstream consumers
    including the result data, confidence score, and cost tracking.
    """

    artifact_id: str
    result_data: str
    confidence_score: float
    cost_consumed: float
    trace_id: str
    metadata: dict[str, Any] = field(default_factory=dict)

    REQUIRED_FIELDS = {"artifact_id", "result_data", "confidence_score", "cost_consumed", "trace_id"}

    def validate(self) -> tuple[bool, list[str]]:
        """Validate output against schema.

        Returns:
            (valid, errors) tuple where valid is True if no errors found.
        """
        errors: list[str] = []
        if not self.artifact_id:
            errors.append("artifact_id is required")
        if not self.trace_id:
            errors.append("trace_id is required")
        if not (0.0 <= self.confidence_score <= 1.0):
            errors.append("confidence_score must be between 0.0 and 1.0")
        if self.cost_consumed < 0:
            errors.append("cost_consumed cannot be negative")
        return len(errors) == 0, errors
