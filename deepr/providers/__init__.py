"""Provider abstraction for multi-cloud Deep Research support."""

import logging
from typing import Literal

from .base import DeepResearchProvider, ResearchRequest, ResearchResponse, ToolConfig
from .openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)

# Track import errors so create_provider can expose root causes.
_OPTIONAL_PROVIDER_IMPORT_ERRORS: dict[str, Exception] = {}

# Optional providers — imported lazily so missing/incompatible SDKs don't break
# the package import for unrelated code paths.
try:
    from .azure_provider import AzureProvider
except Exception as exc:
    AzureProvider = None
    _OPTIONAL_PROVIDER_IMPORT_ERRORS["azure"] = exc

try:
    from .gemini_provider import GeminiProvider
except Exception as exc:
    GeminiProvider = None
    _OPTIONAL_PROVIDER_IMPORT_ERRORS["gemini"] = exc

try:
    from .grok_provider import GrokProvider
except Exception as exc:
    GrokProvider = None
    _OPTIONAL_PROVIDER_IMPORT_ERRORS["xai"] = exc

try:
    from .azure_foundry_provider import AzureFoundryProvider
except Exception as exc:
    AzureFoundryProvider = None
    _OPTIONAL_PROVIDER_IMPORT_ERRORS["azure-foundry"] = exc

ProviderType = Literal["openai", "azure", "gemini", "xai", "azure-foundry"]


def _optional_import_message(provider_type: str, install_hint: str) -> str:
    """Build import error message with root cause when available."""
    root_cause = _OPTIONAL_PROVIDER_IMPORT_ERRORS.get(provider_type)
    if root_cause is None:
        return install_hint

    logger.debug("Optional provider import failed for %s: %s", provider_type, root_cause, exc_info=root_cause)
    return f"{install_hint}. Root cause: {root_cause}"


def create_provider(provider_type: ProviderType, **kwargs) -> DeepResearchProvider:
    """
    Factory function to create the appropriate provider instance.

    Args:
        provider_type: "openai", "azure", "gemini", or "xai"
        **kwargs: Provider-specific configuration

    Returns:
        Initialized provider instance

    Raises:
        ValueError: If provider_type is not supported
    """
    if provider_type == "openai":
        return OpenAIProvider(**kwargs)
    elif provider_type == "azure":
        if AzureProvider is None:
            raise ImportError(
                _optional_import_message("azure", "Azure provider requires: pip install deepr-research[azure]")
            )
        return AzureProvider(**kwargs)
    elif provider_type == "gemini":
        if GeminiProvider is None:
            raise ImportError(
                _optional_import_message("gemini", "Gemini provider requires: pip install google-genai")
            )
        return GeminiProvider(**kwargs)
    elif provider_type == "xai":
        if GrokProvider is None:
            raise ImportError(_optional_import_message("xai", "xAI provider requires: pip install xai-sdk"))
        return GrokProvider(**kwargs)
    elif provider_type == "azure-foundry":
        if AzureFoundryProvider is None:
            raise ImportError(
                _optional_import_message(
                    "azure-foundry", "Azure Foundry provider requires: pip install deepr-research[azure-foundry]"
                )
            )
        return AzureFoundryProvider(**kwargs)
    else:
        raise ValueError(f"Unsupported provider type: {provider_type}")


__all__ = [
    "AzureFoundryProvider",
    "AzureProvider",
    "DeepResearchProvider",
    "GeminiProvider",
    "GrokProvider",
    "OpenAIProvider",
    "ProviderType",
    "ResearchRequest",
    "ResearchResponse",
    "ToolConfig",
    "create_provider",
]
