"""Resolve the provider that owns a persisted research job."""

from typing import Any, cast

from deepr.providers import ProviderType, create_provider
from deepr.providers.base import DeepResearchProvider
from deepr.providers.lazy import config_api_key
from deepr.queue.base import ResearchJob

_API_KEY_FIELDS = {
    "anthropic": "anthropic_api_key",
    "azure": "azure_api_key",
    "gemini": "gemini_api_key",
    "xai": "xai_api_key",
}


def create_job_provider(job: ResearchJob, config: dict[str, Any]) -> DeepResearchProvider:
    """Construct the provider named on a persisted job with its matching key."""
    # Legacy rows may have an empty provider. Default those deterministically
    # to the queue schema's historical OpenAI owner, never to mutable ambient
    # configuration that could route lifecycle calls through another adapter.
    persisted_name = str(job.provider or "openai")
    provider_name = "xai" if persisted_name == "grok" else persisted_name
    if provider_name == "azure-foundry":
        return create_provider(
            "azure-foundry",
            project_endpoint=config.get("azure_foundry_endpoint"),
            deep_research_deployment=config.get("azure_foundry_deep_research_deployment"),
            gpt_deployment=config.get("azure_foundry_gpt_deployment"),
            bing_resource_name=config.get("azure_foundry_bing_resource"),
        )
    key_field = _API_KEY_FIELDS.get(provider_name, "api_key")
    return create_provider(
        cast(ProviderType, provider_name),
        api_key=config_api_key(config.get(key_field)),
    )


__all__ = ["create_job_provider"]
