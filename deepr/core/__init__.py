"""Core business logic exports."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .contracts import (
        Claim,
        DecisionRecord,
        DecisionType,
        ExpertManifest,
        Gap,
        Source,
        TrustClass,
    )
    from .costs import CostController, CostEstimate, CostEstimator
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
    from .settings import Settings

__all__ = [
    "BudgetError",
    "BudgetExceededError",
    "Claim",
    "ConfigurationError",
    "CostController",
    "CostEstimate",
    "CostEstimator",
    "DailyLimitError",
    "DecisionRecord",
    "DecisionType",
    "DeeprError",
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
    "Settings",
    "Source",
    "StorageError",
    "TrustClass",
    "ValidationError",
    "get_safe_test_prompt",
    "get_settings",
    "load_config",
]

_LAZY_IMPORTS = {
    "Claim": (".contracts", "Claim"),
    "DecisionRecord": (".contracts", "DecisionRecord"),
    "DecisionType": (".contracts", "DecisionType"),
    "ExpertManifest": (".contracts", "ExpertManifest"),
    "Gap": (".contracts", "Gap"),
    "Source": (".contracts", "Source"),
    "TrustClass": (".contracts", "TrustClass"),
    "CostController": (".costs", "CostController"),
    "CostEstimate": (".costs", "CostEstimate"),
    "CostEstimator": (".costs", "CostEstimator"),
    "get_safe_test_prompt": (".costs", "get_safe_test_prompt"),
    "DocumentManager": (".documents", "DocumentManager"),
    "BudgetError": (".errors", "BudgetError"),
    "BudgetExceededError": (".errors", "BudgetExceededError"),
    "ConfigurationError": (".errors", "ConfigurationError"),
    "DailyLimitError": (".errors", "DailyLimitError"),
    "DeeprError": (".errors", "DeeprError"),
    "InvalidConfigError": (".errors", "InvalidConfigError"),
    "MissingConfigError": (".errors", "MissingConfigError"),
    "ProviderAuthError": (".errors", "ProviderAuthError"),
    "ProviderError": (".errors", "ProviderError"),
    "ProviderRateLimitError": (".errors", "ProviderRateLimitError"),
    "ProviderTimeoutError": (".errors", "ProviderTimeoutError"),
    "StorageError": (".errors", "StorageError"),
    "ValidationError": (".errors", "ValidationError"),
    "JobManager": (".jobs", "JobManager"),
    "ReportGenerator": (".reports", "ReportGenerator"),
    "ResearchOrchestrator": (".research", "ResearchOrchestrator"),
    "Settings": (".settings", "Settings"),
    "get_settings": (".settings", "get_settings"),
    "load_config": (".settings", "load_config"),
}


def __getattr__(name: str) -> Any:
    """Lazily resolve core symbols."""
    import importlib

    if name not in _LAZY_IMPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr_name = _LAZY_IMPORTS[name]
    module = importlib.import_module(module_name, __name__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
