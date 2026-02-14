"""Provider abstraction for multi-cloud Deep Research support."""

from typing import Literal

from .base import DeepResearchProvider, ResearchRequest, ResearchResponse, ToolConfig
from .openai_provider import OpenAIProvider

# Optional providers — imported lazily so missing SDKs don't break the package
try:
    from .azure_provider import AzureProvider
except ImportError:
    AzureProvider = None

try:
    from .gemini_provider import GeminiProvider
except ImportError:
    GeminiProvider = None

try:
    from .grok_provider import GrokProvider
except ImportError:
    GrokProvider = None

try:
    from .azure_foundry_provider import AzureFoundryProvider
except ImportError:
    AzureFoundryProvider = None

ProviderType = Literal["openai", "azure", "gemini", "xai", "azure-foundry"]


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
            raise ImportError("Azure provider requires: pip install deepr-research[azure]")
        return AzureProvider(**kwargs)
    elif provider_type == "gemini":
        if GeminiProvider is None:
            raise ImportError("Gemini provider requires: pip install google-genai")
        return GeminiProvider(**kwargs)
    elif provider_type == "xai":
        if GrokProvider is None:
            raise ImportError("xAI provider requires: pip install xai-sdk")
        return GrokProvider(**kwargs)
    elif provider_type == "azure-foundry":
        if AzureFoundryProvider is None:
            raise ImportError("Azure Foundry provider requires: pip install deepr-research[azure-foundry]")
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
