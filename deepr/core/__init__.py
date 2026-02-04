"""Core business logic for research orchestration."""

from .research import ResearchOrchestrator
from .jobs import JobManager
from .reports import ReportGenerator
from .documents import DocumentManager
from .costs import CostEstimator, CostController, CostEstimate, get_safe_test_prompt
from .settings import Settings, get_settings, load_config
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
    # Settings
    "Settings",
    "get_settings",
    "load_config",
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
