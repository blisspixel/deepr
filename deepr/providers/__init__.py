"""Provider abstraction for multi-cloud Deep Research support."""

from typing import Literal
from .base import DeepResearchProvider, ResearchRequest, ResearchResponse, ToolConfig
from .openai_provider import OpenAIProvider
from .azure_provider import AzureProvider

ProviderType = Literal["openai", "azure"]


def create_provider(provider_type: ProviderType, **kwargs) -> DeepResearchProvider:
    """
    Factory function to create the appropriate provider instance.

    Args:
        provider_type: Either "openai" or "azure"
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
    else:
        raise ValueError(f"Unsupported provider type: {provider_type}")


__all__ = [
    "DeepResearchProvider",
    "ResearchRequest",
    "ResearchResponse",
    "ToolConfig",
    "OpenAIProvider",
    "AzureProvider",
    "create_provider",
    "ProviderType",
]
