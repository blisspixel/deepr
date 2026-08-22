"""Small filesystem, identifier, and prompt helpers for research commands."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from deepr.core.costs import CostEstimate
    from deepr.experts.research_cost_gate import ResearchCostReservation

_PROVIDER_DEFAULT_MODELS = {
    "openai": "o3-deep-research",
    "azure": "o3-deep-research",
    "gemini": "gemini-3.6-flash",
    "xai": "grok-4.6",
    "grok": "grok-4.6",
}
_BOUNDED_TOOL_PROVIDERS = frozenset({"openai", "azure"})


def ensure_parent_dir(path: str) -> None:
    """Create the parent directory for a configured local path."""
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


async def lookup_cancellable_job(queue: Any, job_id: str) -> tuple[Any, str | None]:
    """Resolve a job that is still eligible for operator cancel."""
    from deepr.queue.base import JobStatus

    full_id = await resolve_job_id(queue, job_id)
    if not full_id:
        return None, "Job not found"
    job = await queue.get_job(full_id)
    if not job:
        return None, "Job not found"
    if job.status is JobStatus.COMPLETED:
        return job, "Job already completed"
    if job.status is JobStatus.FAILED:
        return job, "Job already failed"
    return job, None


async def close_research_cancel(queue: Any, provider: Any, job: Any, default_provider: str) -> None:
    """Cancel one research job and fail closed if queue or cost did not close."""
    import click

    from deepr.services.research_cancellation import cancel_reserved_research

    outcome = await cancel_reserved_research(
        queue=queue,
        provider=provider,
        job=job,
        default_provider=default_provider,
        source=f"cli.research.cancel.{job.id}",
    )
    if not outcome.queue_cancelled:
        raise click.ClickException("Job cancellation could not be confirmed; local state was unchanged")
    if not outcome.confirmed:
        raise click.ClickException("Job was cancelled, but cost or cleanup closure could not be confirmed")


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
    # Code Interpreter is billed by a provider-selected memory tier over a
    # session window. Until callers can bind memory, session count, and
    # duration before dispatch, its maximum marginal cost is not provable.
    return no_web, True


def enforce_monthly_budget_gate(
    estimate: CostEstimate,
    reservation: ResearchCostReservation,
    *,
    yes: bool,
) -> bool:
    """Consult the monthly budget gate for an already-reserved submission.

    Returns True to proceed. On refusal the reservation is refunded and a
    message is emitted. Mirrors run.py semantics: -y skips the confirmation,
    never the gate - a non-interactive caller cannot consent to spend the
    gate flagged for human judgment. The gate was historically wired only
    into `deepr run`, so `deepr research` could spend past the monthly
    budget without it ever being consulted.
    """
    import click

    from deepr.cli.commands.budget import check_budget_approval
    from deepr.experts.research_cost_gate import refund_research_cost

    estimated_cost = float(getattr(estimate, "expected_cost", 0.0) or 0.0)
    if check_budget_approval(estimated_cost):
        return True
    if yes:
        refund_research_cost(reservation)
        click.echo(
            f"Budget gate: estimated ${estimated_cost:.2f} needs confirmation "
            "(over/near the monthly budget, or above the $1 cautious-mode floor) "
            "and -y cannot consent to it. Raise the budget with "
            "'deepr budget set <amount>' to authorize headless spend at this level, "
            "or run interactively.",
            err=True,
        )
        return False
    if not click.confirm(f"Budget gate: proceed with estimated cost ${estimated_cost:.2f}?"):
        refund_research_cost(reservation)
        click.echo("Cancelled")
        return False
    return True


__all__ = [
    "bounded_tool_disable_flags",
    "build_research_prompt",
    "enforce_monthly_budget_gate",
    "ensure_parent_dir",
    "provider_for_model",
    "resolve_job_id",
    "resolve_research_route",
]
