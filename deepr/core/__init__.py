"""Core business logic for research orchestration."""

from .research import ResearchOrchestrator
from .jobs import JobManager
from .reports import ReportGenerator
from .documents import DocumentManager
from .costs import CostEstimator, CostController, CostEstimate, get_safe_test_prompt
from .errors import (
    DeeprError,
    ProviderError,
    ProviderTimeoutError,
    ProviderRateLimitError,
    ProviderAuthError,
    BudgetError,
    BudgetExceededError,
    DailyLimitError,
    ConfigurationError,
    MissingConfigError,
    InvalidConfigError,
    StorageError,
    ValidationError,
)

__all__ = [
    "ResearchOrchestrator",
    "JobManager",
    "ReportGenerator",
    "DocumentManager",
    "CostEstimator",
    "CostController",
    "CostEstimate",
    "get_safe_test_prompt",
    # Errors
    "DeeprError",
    "ProviderError",
    "ProviderTimeoutError",
    "ProviderRateLimitError",
    "ProviderAuthError",
    "BudgetError",
    "BudgetExceededError",
    "DailyLimitError",
    "ConfigurationError",
    "MissingConfigError",
    "InvalidConfigError",
    "StorageError",
    "ValidationError",
]
