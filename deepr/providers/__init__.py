"""Provider abstraction for multi-cloud Deep Research support."""

from typing import Literal
from .base import DeepResearchProvider, ResearchRequest, ResearchResponse, ToolConfig
from .openai_provider import OpenAIProvider
from .azure_provider import AzureProvider
from .gemini_provider import GeminiProvider
from .grok_provider import GrokProvider

ProviderType = Literal["openai", "azure", "gemini", "xai"]


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
        return AzureProvider(**kwargs)
    elif provider_type == "gemini":
        return GeminiProvider(**kwargs)
    elif provider_type == "xai":
        return GrokProvider(**kwargs)
    else:
        raise ValueError(f"Unsupported provider type: {provider_type}")


__all__ = [
    "DeepResearchProvider",
    "ResearchRequest",
    "ResearchResponse",
    "ToolConfig",
    "OpenAIProvider",
    "AzureProvider",
    "GeminiProvider",
    "GrokProvider",
    "create_provider",
    "ProviderType",
]
