"""Core business logic for research orchestration."""

from .contracts import (
    Claim,
    DecisionRecord,
    DecisionType,
    ExpertManifest,
    Gap,
    Source,
    TrustClass,
)
from .costs import CostController, CostEstimate, CostEstimator, get_safe_test_prompt
from .documents import DocumentManager
from .errors import (
    BudgetError,
    BudgetExceededError,
    ConfigurationError,
    DailyLimitError,
    DeeprError,
    InvalidConfigError,
    MissingConfigError,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    StorageError,
    ValidationError,
)
from .jobs import JobManager
from .reports import ReportGenerator
from .research import ResearchOrchestrator
from .settings import Settings, get_settings, load_config

__all__ = [
    "BudgetError",
    "BudgetExceededError",
    # Contracts
    "Claim",
    "ConfigurationError",
    "CostController",
    "CostEstimate",
    "CostEstimator",
    "DailyLimitError",
    # Errors
    "DeeprError",
    "DecisionRecord",
    "DecisionType",
    "DocumentManager",
    "ExpertManifest",
    "Gap",
    "InvalidConfigError",
    "JobManager",
    "MissingConfigError",
    "ProviderAuthError",
    "ProviderError",
    "ProviderRateLimitError",
    "ProviderTimeoutError",
    "ReportGenerator",
    "ResearchOrchestrator",
    # Settings
    "Settings",
    "Source",
    "StorageError",
    "TrustClass",
    "ValidationError",
    "get_safe_test_prompt",
    "get_settings",
    "load_config",
]
