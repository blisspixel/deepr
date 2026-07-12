"""Provider abstraction for multi-cloud Deep Research support."""

from __future__ import annotations

import logging
from importlib import import_module
from typing import TYPE_CHECKING, Any, Literal, cast

from .base import DeepResearchProvider, ResearchRequest, ResearchResponse, ToolConfig

if TYPE_CHECKING:
    from .anthropic_provider import AnthropicProvider
    from .azure_foundry_provider import AzureFoundryProvider
    from .azure_provider import AzureProvider
    from .gemini_provider import GeminiProvider
    from .grok_provider import GrokProvider
    from .openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)

# Track import errors so create_provider can expose root causes.
_OPTIONAL_PROVIDER_IMPORT_ERRORS: dict[str, Exception] = {}

ProviderType = Literal["openai", "anthropic", "azure", "gemini", "xai", "azure-foundry"]

_PROVIDER_EXPORTS: dict[str, tuple[str, str, str, bool]] = {
    "OpenAIProvider": ("openai", ".openai_provider", "OpenAIProvider", False),
    "AnthropicProvider": ("anthropic", ".anthropic_provider", "AnthropicProvider", True),
    "AzureProvider": ("azure", ".azure_provider", "AzureProvider", True),
    "GeminiProvider": ("gemini", ".gemini_provider", "GeminiProvider", True),
    "GrokProvider": ("xai", ".grok_provider", "GrokProvider", True),
    "AzureFoundryProvider": (
        "azure-foundry",
        ".azure_foundry_provider",
        "AzureFoundryProvider",
        True,
    ),
}
_PROVIDER_CLASS_BY_TYPE = {provider_type: export for export, (provider_type, *_rest) in _PROVIDER_EXPORTS.items()}
_PROVIDER_INSTALL_HINTS = {
    "anthropic": "Anthropic provider requires: pip install anthropic",
    "azure": "Azure provider requires: pip install deepr-research[azure]",
    "gemini": "Gemini provider requires: pip install google-genai",
    "xai": "xAI provider requires: pip install xai-sdk",
    "azure-foundry": "Azure Foundry provider requires: pip install deepr-research[azure-foundry]",
}


def __getattr__(name: str) -> Any:
    """Resolve provider implementations only when a caller asks for one."""
    spec = _PROVIDER_EXPORTS.get(name)
    if spec is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    provider_type, module_name, attribute, optional = spec
    try:
        value = getattr(import_module(module_name, __name__), attribute)
    except Exception as exc:
        if not optional:
            raise
        _OPTIONAL_PROVIDER_IMPORT_ERRORS[provider_type] = exc
        value = None
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Include lazy public exports in introspection without importing them."""
    return sorted(set(globals()) | set(_PROVIDER_EXPORTS))


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

    export_name = _PROVIDER_CLASS_BY_TYPE.get(provider_type)
    if export_name is None:
        raise ValueError(f"Unsupported provider type: {provider_type}")

    provider_cls = globals().get(export_name)
    if export_name not in globals():
        provider_cls = __getattr__(export_name)
    if provider_cls is None:
        install_hint = _PROVIDER_INSTALL_HINTS[provider_type]
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
