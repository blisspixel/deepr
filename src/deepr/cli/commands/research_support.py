"""Small filesystem, identifier, and prompt helpers for research commands."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

_PROVIDER_DEFAULT_MODELS = {
    "openai": "o3-deep-research",
    "azure": "o3-deep-research",
    "gemini": "gemini-3.6-flash",
    "xai": "grok-4.3",
    "grok": "grok-4.3",
}
_BOUNDED_TOOL_PROVIDERS = frozenset({"openai", "azure"})


def ensure_parent_dir(path: str) -> None:
    """Create the parent directory for a configured local path."""
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


async def resolve_job_id(queue: Any, maybe_prefix: str) -> str | None:
    """Resolve a full job ID or an unambiguous prefix from the queue."""
    if len(maybe_prefix) >= 32:
        job = await queue.get_job(maybe_prefix)
        return str(job.id) if job else None
    jobs = await queue.list_jobs(limit=500)
    matches = [str(job.id) for job in jobs if str(job.id).startswith(maybe_prefix)]
    return matches[0] if len(matches) == 1 else None


def build_research_prompt(prompt: str, context_content: str | None) -> str:
    """Build the exact provider prompt used for estimation and submission."""
    if not context_content:
        return prompt
    return (
        "## Prior Research Context\n\n"
        "The following prior research may be relevant. Use it as background "
        "but verify and update any findings:\n\n"
        f"---\n{context_content}\n---\n\n"
        f"## New Research Query\n\n{prompt}"
    )


def provider_for_model(model: str) -> str | None:
    """Resolve the provider for a canonical model ID or supported alias."""
    from deepr.providers.registry_pricing import get_resolved_model_capability

    capability = get_resolved_model_capability(model)
    return capability.provider if capability is not None else None


def resolve_research_route(
    provider: str | None,
    model: str | None,
    *,
    environment: Mapping[str, str] | None = None,
) -> tuple[str, str]:
    """Resolve one provider/model pair before preview and execution diverge."""
    env = os.environ if environment is None else environment
    if provider is not None and model is None:
        return provider, _PROVIDER_DEFAULT_MODELS[provider.lower()]
    if model is not None and provider is None:
        inferred_provider = provider_for_model(model)
        if inferred_provider is not None:
            return inferred_provider, model

    is_deep_research = model is None or "deep-research" in model.lower()
    if provider is None:
        provider = env.get(
            "DEEPR_DEEP_RESEARCH_PROVIDER" if is_deep_research else "DEEPR_DEFAULT_PROVIDER",
            "openai" if is_deep_research else "xai",
        )
    if model is None:
        model = env.get(
            "DEEPR_DEEP_RESEARCH_MODEL" if is_deep_research else "DEEPR_DEFAULT_MODEL",
            "o3-deep-research" if is_deep_research else _PROVIDER_DEFAULT_MODELS.get(provider, "grok-4.3"),
        )
    return provider, model


def bounded_tool_disable_flags(provider: str, no_web: bool, no_code: bool) -> tuple[bool, bool]:
    """Apply the currently admitted tool posture for a provider."""
    if provider.lower() not in _BOUNDED_TOOL_PROVIDERS:
        return True, True
    return no_web, no_code


__all__ = [
    "bounded_tool_disable_flags",
    "build_research_prompt",
    "ensure_parent_dir",
    "provider_for_model",
    "resolve_job_id",
    "resolve_research_route",
]
