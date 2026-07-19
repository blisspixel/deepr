"""Structured error types for MCP client operations.

Categorized errors for external tool failures with retry guidance
and budget context for informed decision-making.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MCPErrorCode(str, Enum):
    """Error categories for external MCP tool call failures."""

    TIMEOUT = "TIMEOUT"
    CONNECTION_LOST = "CONNECTION_LOST"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    COST_ACCOUNTING_UNAVAILABLE = "COST_ACCOUNTING_UNAVAILABLE"
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    SERVER_ERROR = "SERVER_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"


# Which error codes are retryable by default
_RETRYABLE_CODES = frozenset(
    {
        MCPErrorCode.TIMEOUT,
        MCPErrorCode.CONNECTION_LOST,
        MCPErrorCode.SERVER_ERROR,
    }
)


@dataclass
class StructuredError:
    """A categorized error from an external MCP tool call.

    Provides enough context for the caller to decide whether to retry,
    use a fallback, or report the gap to the user.
    """

    code: MCPErrorCode
    message: str
    retryable: bool
    fallback_suggestion: str = ""
    budget_shortfall: float = 0.0
    elapsed_seconds: float = 0.0

    def __post_init__(self) -> None:
        if not self.message:
            self.message = f"MCP error: {self.code.value}"
        if self.budget_shortfall < 0.0:
            self.budget_shortfall = 0.0
        if self.elapsed_seconds < 0.0:
            self.elapsed_seconds = 0.0


@dataclass
class BudgetDecision:
    """Result of a pre-call budget check.

    Returned by BudgetPropagator.check_budget() to indicate whether
    a tool call is within budget constraints.
    """

    allowed: bool
    reason: str
    remaining_budget: float
    estimated_cost: float
    shortfall: float = 0.0

    def __post_init__(self) -> None:
        if self.shortfall < 0.0:
            self.shortfall = 0.0
