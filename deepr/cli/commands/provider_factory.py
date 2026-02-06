"""Provider factory for CLI commands.

Centralizes provider initialization logic and API key retrieval.
Reduces complexity in run.py by extracting provider setup.

Requirements: 6.2 - Centralize provider initialization logic
"""

from typing import Optional

from deepr.config import load_config


def get_api_key(provider: str, config: Optional[dict] = None) -> str:
    """Get API key for the specified provider.

    Args:
        provider: Provider name (openai, azure, gemini, grok, xai)
        config: Optional config dict, loads from env if not provided

    Returns:
        API key string

    Raises:
        ValueError: If API key not found for provider
    """
    if config is None:
        config = load_config()

    key_map = {
        "gemini": "gemini_api_key",
        "grok": "xai_api_key",
        "xai": "xai_api_key",
        "azure": "azure_api_key",
        "openai": "api_key",
    }

    config_key = key_map.get(provider, "api_key")
    api_key = config.get(config_key)

    if not api_key:
        raise ValueError(f"No API key found for provider '{provider}'. Set {config_key} in config.")

    return api_key


def create_provider_instance(provider: str, config: Optional[dict] = None):
    """Create a provider instance with the appropriate API key.

    Args:
        provider: Provider name
        config: Optional config dict

    Returns:
        Initialized provider instance
    """
    from deepr.providers import create_provider

    api_key = get_api_key(provider, config)
    return create_provider(provider, api_key=api_key)


def get_tool_name(provider: str, tool_type: str) -> str:
    """Get provider-specific tool name.

    Args:
        provider: Provider name
        tool_type: Generic tool type (web_search, code_interpreter, file_search)

    Returns:
        Provider-specific tool name
    """
    # Grok/xAI uses different tool names
    if provider in ["grok", "xai"]:
        tool_map = {
            "web_search": "web_search",
            "code_interpreter": "code_interpreter",
            "file_search": "file_search",
        }
    else:
        tool_map = {
            "web_search": "web_search_preview",
            "code_interpreter": "code_interpreter",
            "file_search": "file_search",
        }

    return tool_map.get(tool_type, tool_type)


def supports_background_jobs(provider: str) -> bool:
    """Check if provider supports background/async job execution.

    Args:
        provider: Provider name

    Returns:
        True if provider supports background jobs
    """
    return provider in ["openai", "azure"]


def supports_vector_stores(provider: str) -> bool:
    """Check if provider supports vector stores for file search.

    Args:
        provider: Provider name

    Returns:
        True if provider supports vector stores
    """
    return provider in ["openai", "azure"]


def normalize_provider_name(provider: str) -> str:
    """Normalize provider name to canonical form.

    Args:
        provider: Provider name (may be alias)

    Returns:
        Canonical provider name
    """
    aliases = {
        "grok": "xai",
    }
    return aliases.get(provider.lower(), provider.lower())
