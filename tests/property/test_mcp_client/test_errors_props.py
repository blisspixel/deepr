"""Property-based tests for MCP client structured errors.

Feature: mcp-client-agent-interop, Property 32: Structured error completeness and categorization
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from deepr.mcp.client.errors import BudgetDecision, MCPErrorCode, StructuredError

# Strategy for valid error codes
error_codes = st.sampled_from(list(MCPErrorCode))

# Strategy for non-empty messages
messages = st.text(min_size=1, max_size=200).filter(lambda s: s.strip())

# Strategy for structured errors
structured_errors = st.builds(
    StructuredError,
    code=error_codes,
    message=messages,
    retryable=st.booleans(),
    fallback_suggestion=st.text(max_size=100),
    budget_shortfall=st.floats(min_value=-10.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    elapsed_seconds=st.floats(min_value=-10.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
)


# Feature: mcp-client-agent-interop, Property 32: Structured error completeness and categorization


@settings(max_examples=100)
@given(
    code=error_codes,
    message=messages,
    retryable=st.booleans(),
    fallback_suggestion=st.text(max_size=100),
    budget_shortfall=st.floats(min_value=-10.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    elapsed_seconds=st.floats(min_value=-10.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
)
def test_property_32_structured_error_completeness(
    code: MCPErrorCode,
    message: str,
    retryable: bool,
    fallback_suggestion: str,
    budget_shortfall: float,
    elapsed_seconds: float,
) -> None:
    """For any external tool call failure, the returned StructuredError SHALL contain:
    a valid error_code from the defined enum, a non-empty message, and a retryable boolean flag.

    **Validates: Requirements 16.1, 16.2**
    """
    error = StructuredError(
        code=code,
        message=message,
        retryable=retryable,
        fallback_suggestion=fallback_suggestion,
        budget_shortfall=budget_shortfall,
        elapsed_seconds=elapsed_seconds,
    )

    # Error code must be a valid MCPErrorCode member
    assert error.code in MCPErrorCode
    assert isinstance(error.code.value, str)

    # Message must be non-empty
    assert error.message
    assert len(error.message) > 0

    # Retryable must be a boolean
    assert isinstance(error.retryable, bool)

    # Budget shortfall is clamped to non-negative
    assert error.budget_shortfall >= 0.0

    # Elapsed seconds is clamped to non-negative
    assert error.elapsed_seconds >= 0.0


@settings(max_examples=100)
@given(
    code=error_codes,
    retryable=st.booleans(),
)
def test_property_32_empty_message_gets_default(
    code: MCPErrorCode,
    retryable: bool,
) -> None:
    """When message is empty, __post_init__ provides a default message containing the error code.

    **Validates: Requirements 16.1, 16.2**
    """
    error = StructuredError(code=code, message="", retryable=retryable)

    # Default message should contain the error code value
    assert error.code.value in error.message
    assert len(error.message) > 0


@settings(max_examples=100)
@given(
    allowed=st.booleans(),
    reason=st.text(min_size=1, max_size=100),
    remaining_budget=st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    estimated_cost=st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    shortfall=st.floats(min_value=-10.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
)
def test_budget_decision_fields(
    allowed: bool,
    reason: str,
    remaining_budget: float,
    estimated_cost: float,
    shortfall: float,
) -> None:
    """BudgetDecision always has valid fields with non-negative shortfall.

    **Validates: Requirements 16.1, 16.2**
    """
    decision = BudgetDecision(
        allowed=allowed,
        reason=reason,
        remaining_budget=remaining_budget,
        estimated_cost=estimated_cost,
        shortfall=shortfall,
    )

    assert isinstance(decision.allowed, bool)
    assert len(decision.reason) > 0
    assert decision.shortfall >= 0.0
