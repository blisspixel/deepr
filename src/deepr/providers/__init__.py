"""Provider abstraction for multi-cloud Deep Research support."""

import logging
from typing import Any, Literal, cast

from .base import DeepResearchProvider, ResearchRequest, ResearchResponse, ToolConfig
from .openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)

# Track import errors so create_provider can expose root causes.
_OPTIONAL_PROVIDER_IMPORT_ERRORS: dict[str, Exception] = {}

# Optional providers - imported lazily so missing/incompatible SDKs don't break
# the package import for unrelated code paths.
try:
    from .anthropic_provider import AnthropicProvider
except Exception as exc:
    AnthropicProvider = None  # type: ignore[assignment,misc]
    _OPTIONAL_PROVIDER_IMPORT_ERRORS["anthropic"] = exc

try:
    from .azure_provider import AzureProvider
except Exception as exc:
    AzureProvider = None  # type: ignore[assignment,misc]
    _OPTIONAL_PROVIDER_IMPORT_ERRORS["azure"] = exc

try:
    from .gemini_provider import GeminiProvider
except Exception as exc:
    GeminiProvider = None  # type: ignore[assignment,misc]
    _OPTIONAL_PROVIDER_IMPORT_ERRORS["gemini"] = exc

try:
    from .grok_provider import GrokProvider
except Exception as exc:
    GrokProvider = None  # type: ignore[assignment,misc]
    _OPTIONAL_PROVIDER_IMPORT_ERRORS["xai"] = exc

try:
    from .azure_foundry_provider import AzureFoundryProvider
except Exception as exc:
    AzureFoundryProvider = None  # type: ignore[assignment,misc]
    _OPTIONAL_PROVIDER_IMPORT_ERRORS["azure-foundry"] = exc

ProviderType = Literal["openai", "anthropic", "azure", "gemini", "xai", "azure-foundry"]


def _optional_import_message(provider_type: str, install_hint: str) -> str:
    """Build import error message with root cause when available."""
    root_cause = _OPTIONAL_PROVIDER_IMPORT_ERRORS.get(provider_type)
    if root_cause is None:
        return install_hint

    logger.debug("Optional provider import failed for %s: %s", provider_type, root_cause, exc_info=root_cause)
    return f"{install_hint}. Root cause: {root_cause}"


def create_provider(provider_type: ProviderType, **kwargs: Any) -> DeepResearchProvider:
    """
    Factory function to create the appropriate provider instance.

    Args:
        provider_type: "openai", "anthropic", "azure", "gemini", "xai", or "azure-foundry"
        **kwargs: Provider-specific configuration

    Returns:
        Initialized provider instance

    Raises:
        ValueError: If provider_type is not supported
    """
    # load_config() redacts secrets to "***" (so the config dict can be
    # logged/serialized safely). Callers historically passed that dict's
    # api_key straight through, which would override every provider's
    # env-var fallback with a masked string and 401 at the first real
    # call. Treat the placeholder (or empty string) as "not provided".
    if kwargs.get("api_key") in ("***", ""):
        kwargs["api_key"] = None

    if provider_type == "openai":
        return OpenAIProvider(**kwargs)

    optional_providers: dict[str, tuple[Any | None, str]] = {
        "anthropic": (AnthropicProvider, "Anthropic provider requires: pip install anthropic"),
        "azure": (AzureProvider, "Azure provider requires: pip install deepr-research[azure]"),
        "gemini": (GeminiProvider, "Gemini provider requires: pip install google-genai"),
        "xai": (GrokProvider, "xAI provider requires: pip install xai-sdk"),
        "azure-foundry": (
            AzureFoundryProvider,
            "Azure Foundry provider requires: pip install deepr-research[azure-foundry]",
        ),
    }
    provider_info = optional_providers.get(provider_type)
    if provider_info is None:
        raise ValueError(f"Unsupported provider type: {provider_type}")

    provider_cls, install_hint = provider_info
    if provider_cls is None:
        raise ImportError(_optional_import_message(provider_type, install_hint))
    return cast(DeepResearchProvider, provider_cls(**kwargs))


__all__ = [
    "AnthropicProvider",
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
