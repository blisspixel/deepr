"""Core exception hierarchy for Deepr.

This module defines the base exception classes used throughout Deepr.
All Deepr exceptions inherit from DeeprError, enabling both specific
and broad exception handling.

Exception Hierarchy:
    DeeprError (base)
    ├── ProviderError - LLM provider issues
    │   ├── ProviderTimeoutError
    │   ├── ProviderRateLimitError
    │   └── ProviderAuthError
    ├── BudgetError - Cost/budget issues
    │   ├── BudgetExceededError
    │   └── DailyLimitError
    ├── ConfigurationError - Config issues
    │   ├── MissingConfigError
    │   └── InvalidConfigError
    ├── StorageError - Storage issues
    │   ├── FileNotFoundError
    │   └── PermissionError
    └── ValidationError - Input validation
        ├── InvalidInputError
        └── SchemaValidationError
"""

from typing import Any


class DeeprError(Exception):
    """Base exception for all Deepr errors.

    All Deepr-specific exceptions inherit from this class, allowing
    callers to catch all Deepr errors with a single except clause.

    Attributes:
        message: Human-readable error message
        error_code: Machine-readable error code (e.g., "PROVIDER_TIMEOUT")
        category: Broad failure class an agent can branch on without parsing
            the code (e.g. "provider", "auth", "budget", "config",
            "storage", "validation", "internal")
        retryable: Whether retrying the same call could plausibly succeed
            (transient failures: timeouts, rate limits, upstream outages).
            Auth/budget/config/validation errors are not retryable - they
            need an action, not a wait.
        details: Optional dict with additional context. A "retry_after"
            key (seconds) is surfaced at the top level of to_dict().
    """

    error_code: str = "DEEPR_ERROR"
    category: str = "internal"
    retryable: bool = False

    def __init__(self, message: str, error_code: str | None = None, details: dict[str, Any] | None = None):
        self.message = message
        if error_code:
            self.error_code = error_code
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to a machine-parseable dict for agents/APIs.

        Carries the RFC 9457 / agent-error fields (category, retryable,
        retry_after) alongside the original code+message so a consumer can
        classify the failure and drive backoff without scraping prose.
        Additive: the original keys are unchanged.
        """
        payload: dict[str, Any] = {
            "error": True,
            "error_code": self.error_code,
            "category": self.category,
            "retryable": self.retryable,
            "message": self.message,
            "details": self.details,
        }
        retry_after = self.details.get("retry_after")
        if retry_after is not None:
            payload["retry_after"] = retry_after
        return payload


# Provider Errors
class ProviderError(DeeprError):
    """Base class for LLM provider errors."""

    error_code = "PROVIDER_ERROR"
    category = "provider"
    # Generic provider failures are conservatively non-retryable; specific
    # transient subclasses opt in below.


class ProviderTimeoutError(ProviderError):
    """Provider API call timed out."""

    error_code = "PROVIDER_TIMEOUT"
    retryable = True

    def __init__(self, provider: str, timeout_seconds: int):
        super().__init__(
            f"{provider} API call timed out after {timeout_seconds}s. "
            f"The service may be overloaded - try again in a few minutes.",
            details={"provider": provider, "timeout_seconds": timeout_seconds},
        )


class ProviderRateLimitError(ProviderError):
    """Provider rate limit exceeded."""

    error_code = "PROVIDER_RATE_LIMIT"
    retryable = True

    def __init__(self, provider: str, retry_after: int | None = None):
        msg = f"{provider} rate limit exceeded."
        if retry_after:
            msg += f" Retry after {retry_after} seconds."
        super().__init__(msg, details={"provider": provider, "retry_after": retry_after})


class ProviderAuthError(ProviderError):
    """Provider authentication failed."""

    error_code = "PROVIDER_AUTH"
    category = "auth"  # actionable (fix the key), not retryable

    def __init__(self, provider: str, key_name: str = "API_KEY"):
        super().__init__(
            f"{provider} authentication failed. Check your {key_name} environment variable.",
            details={"provider": provider, "key_name": key_name},
        )


class ProviderUnavailableError(ProviderError):
    """Provider service is unavailable."""

    error_code = "PROVIDER_UNAVAILABLE"
    retryable = True

    def __init__(self, provider: str, status_code: int | None = None):
        msg = f"{provider} service is currently unavailable."
        if status_code:
            msg += f" (HTTP {status_code})"
        super().__init__(msg, details={"provider": provider, "status_code": status_code})


# Budget Errors
class BudgetError(DeeprError):
    """Base class for budget/cost errors."""

    error_code = "BUDGET_ERROR"
    category = "budget"  # needs a higher budget or reset, not a retry


class BudgetExceededError(BudgetError):
    """Operation would exceed budget limit."""

    error_code = "BUDGET_EXCEEDED"

    def __init__(self, estimated_cost: float, budget_limit: float, operation: str = "operation"):
        super().__init__(
            f"Estimated cost (${estimated_cost:.2f}) exceeds budget (${budget_limit:.2f}) for {operation}.",
            details={"estimated_cost": estimated_cost, "budget_limit": budget_limit, "operation": operation},
        )


class DailyLimitError(BudgetError):
    """Daily spending limit reached."""

    error_code = "DAILY_LIMIT"

    def __init__(self, daily_spent: float, daily_limit: float):
        super().__init__(
            f"Daily spending limit reached (${daily_spent:.2f}/${daily_limit:.2f}). Limit resets at midnight UTC.",
            details={"daily_spent": daily_spent, "daily_limit": daily_limit},
        )


# Configuration Errors
class ConfigurationError(DeeprError):
    """Base class for configuration errors."""

    error_code = "CONFIG_ERROR"
    category = "config"


class MissingConfigError(ConfigurationError):
    """Required configuration is missing."""

    error_code = "MISSING_CONFIG"

    def __init__(self, config_key: str, source: str = "environment"):
        super().__init__(
            f"Required configuration '{config_key}' not found in {source}.",
            details={"config_key": config_key, "source": source},
        )


class InvalidConfigError(ConfigurationError):
    """Configuration value is invalid."""

    error_code = "INVALID_CONFIG"

    def __init__(self, config_key: str, value: Any, reason: str):
        super().__init__(
            f"Invalid value for '{config_key}': {reason}",
            details={"config_key": config_key, "value": str(value), "reason": reason},
        )


# Storage Errors
class StorageError(DeeprError):
    """Base class for storage errors."""

    error_code = "STORAGE_ERROR"
    category = "storage"


class FileNotFoundError(StorageError):
    """Required file not found."""

    error_code = "FILE_NOT_FOUND"

    def __init__(self, filepath: str):
        super().__init__(f"File not found: {filepath}", details={"filepath": filepath})


class StoragePermissionError(StorageError):
    """Insufficient permissions for storage operation."""

    error_code = "STORAGE_PERMISSION"

    def __init__(self, filepath: str, operation: str = "access"):
        super().__init__(
            f"Permission denied: cannot {operation} '{filepath}'",
            details={"filepath": filepath, "operation": operation},
        )


# Validation Errors
class ValidationError(DeeprError):
    """Base class for validation errors."""

    error_code = "VALIDATION_ERROR"
    category = "validation"


class InvalidInputError(ValidationError):
    """User input is invalid."""

    error_code = "INVALID_INPUT"

    def __init__(self, field: str, reason: str):
        super().__init__(f"Invalid input for '{field}': {reason}", details={"field": field, "reason": reason})


class SchemaValidationError(ValidationError):
    """Data does not match expected schema."""

    error_code = "SCHEMA_VALIDATION"

    def __init__(self, schema_name: str, errors: list[str]) -> None:
        super().__init__(
            f"Schema validation failed for '{schema_name}': {', '.join(errors)}",
            details={"schema_name": schema_name, "errors": errors},
        )


# Expert System Errors (re-export from experts.errors for convenience)
# These are more specific and live in deepr/experts/errors.py
