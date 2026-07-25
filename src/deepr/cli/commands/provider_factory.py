"""Provider factory for CLI commands.

Centralizes provider initialization logic and API key retrieval.
Reduces complexity in run.py by extracting provider setup.

Requirements: 6.2 - Centralize provider initialization logic
"""

import os

from deepr.config import load_config

# load_config() deliberately redacts or omits provider credentials, so the
# environment (populated from .env by deepr.config's load_dotenv) is the actual
# source of truth for keys. The config dict is consulted first only so tests
# and callers that inject explicit keys keep working.
_ENV_KEY_MAP = {
    "gemini": "GEMINI_API_KEY",
    "grok": "XAI_API_KEY",
    "xai": "XAI_API_KEY",
    "azure": "AZURE_OPENAI_API_KEY",
    "azure-foundry": "AZURE_PROJECT_ENDPOINT",
    "openai": "OPENAI_API_KEY",
}


def get_api_key(provider: str, config: dict | None = None) -> str:
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
        "azure-foundry": "azure_foundry_endpoint",
        "openai": "api_key",
    }

    config_key = key_map.get(provider, "api_key")
    api_key = config.get(config_key)

    # The redaction placeholder is not a credential; treat it as absent so the
    # environment fallback below can supply the real key.
    if api_key in ("***", ""):
        api_key = None

    if not api_key:
        # load_config() intentionally carries no real credentials ("callers
        # needing real keys should use env"), so honor that contract here.
        # Without this fallback every non-OpenAI provider failed with a missing
        # key even when the key was present in the environment, and the failure
        # surfaced downstream as a misleading "authentication failed".
        env_var = _ENV_KEY_MAP.get(provider)
        if env_var:
            api_key = os.getenv(env_var) or None

    if not api_key:
        env_hint = _ENV_KEY_MAP.get(provider, "the provider's API key variable")
        raise ValueError(f"No API key found for provider '{provider}'. Set {env_hint} in .env or the environment.")

    return api_key


def create_provider_instance(provider: str, config: dict | None = None):
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
    return provider in ["openai", "azure", "azure-foundry"]


def supports_vector_stores(provider: str) -> bool:
    """Check if provider supports vector stores for file search.

    Args:
        provider: Provider name

    Returns:
        True if provider supports vector stores
    """
    return provider in ["openai", "azure"]  # azure-foundry uses Bing grounding, not vector stores


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
