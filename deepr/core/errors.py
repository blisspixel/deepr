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

from typing import Optional, Dict, Any


class DeeprError(Exception):
    """Base exception for all Deepr errors.
    
    All Deepr-specific exceptions inherit from this class, allowing
    callers to catch all Deepr errors with a single except clause.
    
    Attributes:
        message: Human-readable error message
        error_code: Machine-readable error code (e.g., "PROVIDER_TIMEOUT")
        details: Optional dict with additional context
    """
    
    error_code: str = "DEEPR_ERROR"
    
    def __init__(
        self, 
        message: str, 
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        if error_code:
            self.error_code = error_code
        self.details = details or {}
        super().__init__(message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dict for API responses."""
        return {
            "error": True,
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details
        }


# Provider Errors
class ProviderError(DeeprError):
    """Base class for LLM provider errors."""
    error_code = "PROVIDER_ERROR"


class ProviderTimeoutError(ProviderError):
    """Provider API call timed out."""
    error_code = "PROVIDER_TIMEOUT"
    
    def __init__(self, provider: str, timeout_seconds: int):
        super().__init__(
            f"{provider} API call timed out after {timeout_seconds}s. "
            f"The service may be overloaded - try again in a few minutes.",
            details={"provider": provider, "timeout_seconds": timeout_seconds}
        )


class ProviderRateLimitError(ProviderError):
    """Provider rate limit exceeded."""
    error_code = "PROVIDER_RATE_LIMIT"
    
    def __init__(self, provider: str, retry_after: Optional[int] = None):
        msg = f"{provider} rate limit exceeded."
        if retry_after:
            msg += f" Retry after {retry_after} seconds."
        super().__init__(msg, details={"provider": provider, "retry_after": retry_after})


class ProviderAuthError(ProviderError):
    """Provider authentication failed."""
    error_code = "PROVIDER_AUTH"
    
    def __init__(self, provider: str, key_name: str = "API_KEY"):
        super().__init__(
            f"{provider} authentication failed. Check your {key_name} environment variable.",
            details={"provider": provider, "key_name": key_name}
        )


class ProviderUnavailableError(ProviderError):
    """Provider service is unavailable."""
    error_code = "PROVIDER_UNAVAILABLE"
    
    def __init__(self, provider: str, status_code: Optional[int] = None):
        msg = f"{provider} service is currently unavailable."
        if status_code:
            msg += f" (HTTP {status_code})"
        super().__init__(msg, details={"provider": provider, "status_code": status_code})


# Budget Errors
class BudgetError(DeeprError):
    """Base class for budget/cost errors."""
    error_code = "BUDGET_ERROR"


class BudgetExceededError(BudgetError):
    """Operation would exceed budget limit."""
    error_code = "BUDGET_EXCEEDED"
    
    def __init__(self, estimated_cost: float, budget_limit: float, operation: str = "operation"):
        super().__init__(
            f"Estimated cost (${estimated_cost:.2f}) exceeds budget (${budget_limit:.2f}) for {operation}.",
            details={
                "estimated_cost": estimated_cost,
                "budget_limit": budget_limit,
                "operation": operation
            }
        )


class DailyLimitError(BudgetError):
    """Daily spending limit reached."""
    error_code = "DAILY_LIMIT"
    
    def __init__(self, daily_spent: float, daily_limit: float):
        super().__init__(
            f"Daily spending limit reached (${daily_spent:.2f}/${daily_limit:.2f}). "
            f"Limit resets at midnight UTC.",
            details={"daily_spent": daily_spent, "daily_limit": daily_limit}
        )


# Configuration Errors
class ConfigurationError(DeeprError):
    """Base class for configuration errors."""
    error_code = "CONFIG_ERROR"


class MissingConfigError(ConfigurationError):
    """Required configuration is missing."""
    error_code = "MISSING_CONFIG"
    
    def __init__(self, config_key: str, source: str = "environment"):
        super().__init__(
            f"Required configuration '{config_key}' not found in {source}.",
            details={"config_key": config_key, "source": source}
        )


class InvalidConfigError(ConfigurationError):
    """Configuration value is invalid."""
    error_code = "INVALID_CONFIG"
    
    def __init__(self, config_key: str, value: Any, reason: str):
        super().__init__(
            f"Invalid value for '{config_key}': {reason}",
            details={"config_key": config_key, "value": str(value), "reason": reason}
        )


# Storage Errors
class StorageError(DeeprError):
    """Base class for storage errors."""
    error_code = "STORAGE_ERROR"


class FileNotFoundError(StorageError):
    """Required file not found."""
    error_code = "FILE_NOT_FOUND"
    
    def __init__(self, filepath: str):
        super().__init__(
            f"File not found: {filepath}",
            details={"filepath": filepath}
        )


class StoragePermissionError(StorageError):
    """Insufficient permissions for storage operation."""
    error_code = "STORAGE_PERMISSION"
    
    def __init__(self, filepath: str, operation: str = "access"):
        super().__init__(
            f"Permission denied: cannot {operation} '{filepath}'",
            details={"filepath": filepath, "operation": operation}
        )


# Validation Errors
class ValidationError(DeeprError):
    """Base class for validation errors."""
    error_code = "VALIDATION_ERROR"


class InvalidInputError(ValidationError):
    """User input is invalid."""
    error_code = "INVALID_INPUT"
    
    def __init__(self, field: str, reason: str):
        super().__init__(
            f"Invalid input for '{field}': {reason}",
            details={"field": field, "reason": reason}
        )


class SchemaValidationError(ValidationError):
    """Data does not match expected schema."""
    error_code = "SCHEMA_VALIDATION"
    
    def __init__(self, schema_name: str, errors: list):
        super().__init__(
            f"Schema validation failed for '{schema_name}': {', '.join(errors)}",
            details={"schema_name": schema_name, "errors": errors}
        )


# Expert System Errors (re-export from experts.errors for convenience)
# These are more specific and live in deepr/experts/errors.py
