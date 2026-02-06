"""
Trajectory metrics tracking for agent evaluation.

Tracks:
- Trajectory efficiency: How close to optimal path
- Citation accuracy: Percentage of claims with sources
- Hallucination rate: Invented parameters or facts
- Context economy: Tokens consumed per task
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class StepType(Enum):
    """Types of trajectory steps."""

    TOOL_CALL = "tool_call"
    RESOURCE_READ = "resource_read"
    ELICITATION = "elicitation"
    RESPONSE = "response"
    ERROR = "error"


@dataclass
class TrajectoryStep:
    """A single step in an agent trajectory."""

    step_type: StepType
    tool_name: Optional[str] = None
    parameters: dict = field(default_factory=dict)
    tokens_used: int = 0
    timestamp: datetime = field(default_factory=datetime.now)
    success: bool = True
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "step_type": self.step_type.value,
            "tool_name": self.tool_name,
            "parameters": self.parameters,
            "tokens_used": self.tokens_used,
            "timestamp": self.timestamp.isoformat(),
            "success": self.success,
            "error_message": self.error_message,
        }


@dataclass
class TrajectoryMetrics:
    """Aggregated metrics for a trajectory."""

    total_steps: int = 0
    optimal_steps: int = 0
    efficiency: float = 1.0

    total_claims: int = 0
    cited_claims: int = 0
    citation_accuracy: float = 1.0

    total_parameters: int = 0
    hallucinated_parameters: int = 0
    hallucination_rate: float = 0.0

    total_tokens: int = 0
    tasks_completed: int = 0
    tokens_per_task: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "efficiency": {
                "total_steps": self.total_steps,
                "optimal_steps": self.optimal_steps,
                "efficiency": self.efficiency,
            },
            "citation_accuracy": {
                "total_claims": self.total_claims,
                "cited_claims": self.cited_claims,
                "accuracy": self.citation_accuracy,
            },
            "hallucination": {
                "total_parameters": self.total_parameters,
                "hallucinated": self.hallucinated_parameters,
                "rate": self.hallucination_rate,
            },
            "context_economy": {
                "total_tokens": self.total_tokens,
                "tasks_completed": self.tasks_completed,
                "tokens_per_task": self.tokens_per_task,
            },
        }

    def passes_targets(
        self,
        efficiency_target: float = 0.9,
        citation_target: float = 0.95,
        hallucination_target: float = 0.01,
        tokens_target: int = 10000,
    ) -> tuple[bool, list[str]]:
        """
        Check if metrics pass target thresholds.

        Returns:
            Tuple of (passes_all, list of failures)
        """
        failures = []

        if self.efficiency < efficiency_target:
            failures.append(f"Efficiency {self.efficiency:.2%} < target {efficiency_target:.2%}")

        if self.citation_accuracy < citation_target:
            failures.append(f"Citation accuracy {self.citation_accuracy:.2%} < target {citation_target:.2%}")

        if self.hallucination_rate > hallucination_target:
            failures.append(f"Hallucination rate {self.hallucination_rate:.2%} > target {hallucination_target:.2%}")

        if self.tokens_per_task > tokens_target:
            failures.append(f"Tokens per task {self.tokens_per_task:.0f} > target {tokens_target}")

        return len(failures) == 0, failures


class MetricsTracker:
    """Tracks trajectory metrics during agent execution."""

    def __init__(self, golden_path: Optional[list[str]] = None):
        """
        Initialize tracker.

        Args:
            golden_path: Optional list of expected tool calls for optimal path
        """
        self.steps: list[TrajectoryStep] = []
        self.golden_path = golden_path or []
        self.known_schemas: dict[str, set[str]] = {}

    def add_step(self, step: TrajectoryStep) -> None:
        """Record a trajectory step."""
        self.steps.append(step)

    def record_tool_call(
        self,
        tool_name: str,
        parameters: dict,
        tokens: int = 0,
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        """Record a tool call step."""
        self.add_step(
            TrajectoryStep(
                step_type=StepType.TOOL_CALL,
                tool_name=tool_name,
                parameters=parameters,
                tokens_used=tokens,
                success=success,
                error_message=error,
            )
        )

    def record_resource_read(
        self,
        resource_uri: str,
        tokens: int = 0,
    ) -> None:
        """Record a resource read step."""
        self.add_step(
            TrajectoryStep(
                step_type=StepType.RESOURCE_READ,
                tool_name=resource_uri,
                tokens_used=tokens,
            )
        )

    def record_elicitation(
        self,
        elicitation_type: str,
        response: str,
        tokens: int = 0,
    ) -> None:
        """Record an elicitation step."""
        self.add_step(
            TrajectoryStep(
                step_type=StepType.ELICITATION,
                tool_name=elicitation_type,
                parameters={"response": response},
                tokens_used=tokens,
            )
        )

    def register_schema(self, tool_name: str, valid_params: set[str]) -> None:
        """Register valid parameters for a tool schema."""
        self.known_schemas[tool_name] = valid_params

    def calculate_metrics(self) -> TrajectoryMetrics:
        """Calculate all trajectory metrics."""
        metrics = TrajectoryMetrics()

        # Efficiency
        metrics.total_steps = len(self.steps)
        metrics.optimal_steps = len(self.golden_path) if self.golden_path else metrics.total_steps
        metrics.efficiency = calculate_efficiency(self.steps, self.golden_path)

        # Tokens
        metrics.total_tokens = sum(s.tokens_used for s in self.steps)
        metrics.tasks_completed = sum(1 for s in self.steps if s.step_type == StepType.TOOL_CALL and s.success)
        metrics.tokens_per_task = calculate_context_economy(metrics.total_tokens, metrics.tasks_completed)

        # Hallucinations
        hallucination_result = detect_hallucinations(self.steps, self.known_schemas)
        metrics.total_parameters = hallucination_result["total"]
        metrics.hallucinated_parameters = hallucination_result["hallucinated"]
        metrics.hallucination_rate = hallucination_result["rate"]

        return metrics

    def reset(self) -> None:
        """Clear all recorded steps."""
        self.steps = []


def calculate_efficiency(
    steps: list[TrajectoryStep],
    golden_path: list[str],
) -> float:
    """
    Calculate trajectory efficiency compared to golden path.

    Efficiency measures how close the actual trajectory is to the optimal
    path. A value of 1.0 means the agent took exactly the optimal number
    of steps. Values below 1.0 indicate extra steps were taken.

    Formula: efficiency = optimal_steps / actual_steps

    Args:
        steps: Actual trajectory steps taken
        golden_path: List of expected tool names in optimal order

    Returns:
        Efficiency ratio (0.0 to 1.0, higher is better)
        Returns 1.0 for empty trajectories (no steps = no inefficiency)

    Note:
        Efficiency is capped at 1.0 - taking fewer steps than optimal
        still counts as 100% efficient (the golden path may be conservative).
    """
    if not steps:
        return 1.0

    actual_steps = len(steps)
    optimal_steps = len(golden_path) if golden_path else actual_steps

    # Avoid division by zero
    if actual_steps == 0:
        return 1.0

    # Efficiency is ratio of optimal to actual
    # Capped at 1.0 (can't be more efficient than optimal)
    return min(1.0, optimal_steps / actual_steps)


def calculate_citation_accuracy(
    text: str,
    total_claims: Optional[int] = None,
) -> tuple[float, int, int]:
    """
    Calculate citation accuracy in text.

    Analyzes text to determine what percentage of factual claims
    have proper citations. Uses heuristics to identify claims
    (sentences with numbers, percentages, dates, etc.).

    Citation patterns recognized:
    - [1], [2], etc. (numeric references)

    Args:
        text: Text to analyze
        total_claims: Optional override for total claim count.
                     If not provided, claims are estimated heuristically.

    Returns:
        Tuple of (accuracy, cited_claims, total_claims)
        - accuracy: 0.0 to 1.0, percentage of claims with citations
        - cited_claims: Number of unique citation references found
        - total_claims: Total claims (provided or estimated)

    Note:
        This is a heuristic measure. For precise citation tracking,
        use structured citation metadata instead.
    """
    # Handle empty text
    if not text or not text.strip():
        return 1.0, 0, 0

    # Find all citation references
    citation_pattern = r"\[\d+\]"
    citations = re.findall(citation_pattern, text)
    cited_count = len(set(citations))

    # Estimate total claims by counting sentences with factual assertions
    # This is a heuristic - sentences with numbers, percentages, or specific claims
    claim_patterns = [
        r"\d+%",  # Percentages
        r"\$[\d,]+",  # Dollar amounts
        r"\d{4}",  # Years
        r"according to",  # Attribution phrases
        r"research shows",
        r"studies indicate",
    ]

    if total_claims is None:
        # Count sentences that look like claims
        sentences = text.split(".")
        claim_count = 0
        for sentence in sentences:
            for pattern in claim_patterns:
                if re.search(pattern, sentence, re.IGNORECASE):
                    claim_count += 1
                    break
        total_claims = max(claim_count, cited_count)

    if total_claims == 0:
        return 1.0, 0, 0

    accuracy = cited_count / total_claims if total_claims > 0 else 1.0
    return min(1.0, accuracy), cited_count, total_claims


def detect_hallucinations(
    steps: list[TrajectoryStep],
    known_schemas: dict[str, set[str]],
) -> dict:
    """
    Detect hallucinated parameters in tool calls.

    A hallucination is a parameter that doesn't exist in the tool schema.

    Args:
        steps: Trajectory steps to analyze
        known_schemas: Map of tool_name -> set of valid parameter names

    Returns:
        Dict with total, hallucinated, and rate
    """
    total_params = 0
    hallucinated = 0

    for step in steps:
        if step.step_type != StepType.TOOL_CALL:
            continue

        if step.tool_name not in known_schemas:
            # Unknown tool - can't verify
            continue

        valid_params = known_schemas[step.tool_name]
        for param_name in step.parameters.keys():
            total_params += 1
            if param_name not in valid_params:
                hallucinated += 1

    rate = hallucinated / total_params if total_params > 0 else 0.0

    return {
        "total": total_params,
        "hallucinated": hallucinated,
        "rate": rate,
    }


def calculate_context_economy(
    total_tokens: int,
    tasks_completed: int,
) -> float:
    """
    Calculate tokens per task metric.

    Args:
        total_tokens: Total tokens consumed
        tasks_completed: Number of tasks completed

    Returns:
        Tokens per task (lower is better)
    """
    if tasks_completed == 0:
        return float(total_tokens) if total_tokens > 0 else 0.0

    return total_tokens / tasks_completed
