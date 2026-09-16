"""Attended one-shot OpenRouter research under wallet, reservation, and ledger."""

from __future__ import annotations

import uuid
from pathlib import Path

import click

from deepr.cli.colors import console, print_header, print_key_value
from deepr.cli.commands.budget import check_budget_approval
from deepr.core.cost_caps import paid_api_provider_scope, resolve_spend_caps
from deepr.experts.parent_budget_transaction import open_parent_budget_transaction
from deepr.experts.research_cost_gate import (
    ResearchCostBlocked,
    refund_research_cost,
    reserve_research_cost,
    settle_research_cost,
)
from deepr.experts.research_reservation_store import ResearchReservationStore
from deepr.providers.base import ResearchRequest
from deepr.providers.dispatch_authority import require_unproxied_paid_transport
from deepr.providers.openrouter_account_controls import load_openrouter_api_key
from deepr.providers.openrouter_completion import (
    OpenRouterCompletionError,
    OpenRouterCompletionResult,
    complete_openrouter_chat,
)
from deepr.providers.registry_pricing import get_resolved_model_capability
from deepr.security.key_quarantine import temporarily_released_metered_keys
from deepr.services.research_bounds import bounded_research_cost_estimate

_ATTENDED_MAX_INPUT_TOKENS = 8_000
_ATTENDED_MAX_OUTPUT_TOKENS = 4_000
_SYSTEM = (
    "You are a research assistant for Deepr, an open-source tool that turns "
    "research into persistent domain experts (beliefs, confidence, gaps, citations) "
    "under explicit capacity bounds. Write a concise, structured memo. Distinguish "
    "established practice from speculation. Name evaluation traps. Do not claim "
    "Deepr already has a capability unless the prompt says it does."
)


def _confirm_openrouter_spend(*, max_cost: float, yes: bool) -> None:
    if check_budget_approval(max_cost):
        return
    if yes:
        raise click.ClickException(f"Budget gate: estimated ${max_cost:.4f} needs confirmation and -y cannot consent")
    if not click.confirm(f"Spend up to ${max_cost:.4f} on one OpenRouter completion?"):
        raise click.ClickException("Cancelled")


def _dispatch_openrouter_completion(
    *,
    model: str,
    query: str,
    max_tokens: int,
    prompt_max_price: float,
    completion_max_price: float,
) -> OpenRouterCompletionResult:
    api_key = load_openrouter_api_key()
    if not api_key:
        raise click.ClickException("OPENROUTER_API_KEY is not available")
    try:
        with temporarily_released_metered_keys(key_names=("OPENROUTER_API_KEY",)):
            return complete_openrouter_chat(
                api_key=api_key,
                model=model,
                system_message=_SYSTEM,
                prompt=query,
                max_tokens=max_tokens,
                prompt_max_price=prompt_max_price,
                completion_max_price=completion_max_price,
            )
    except OpenRouterCompletionError as exc:
        raise click.ClickException(str(exc)) from exc
    finally:
        api_key = ""


def run_attended_openrouter_research(
    *,
    query: str,
    model: str,
    limit: float | None,
    yes: bool,
    no_web: bool,
    no_code: bool,
    upload: tuple[str, ...],
    scrape: str | None,
) -> None:
    """Run one pinned OpenRouter completion and print the settled memo."""
    if upload or scrape:
        raise click.ClickException("Attended OpenRouter research cannot take uploads or scrape targets")
    if not no_web or not no_code:
        raise click.ClickException("Attended OpenRouter research requires --no-web and disabled code tools")
    capability = get_resolved_model_capability(model)
    if capability is None or capability.provider != "openrouter":
        raise click.ClickException(f"No OpenRouter catalog contract for model {model!r}")
    request = ResearchRequest(
        prompt=query,
        model=model,
        system_message=_SYSTEM,
        tools=[],
        max_input_tokens=min(_ATTENDED_MAX_INPUT_TOKENS, capability.context_window),
        max_output_tokens=min(
            _ATTENDED_MAX_OUTPUT_TOKENS,
            capability.max_output_tokens or _ATTENDED_MAX_OUTPUT_TOKENS,
        ),
        max_tool_calls=1,
        max_provider_requests=1,
        background=False,
        store=False,
    )
    with paid_api_provider_scope("openrouter"):
        estimate = bounded_research_cost_estimate(
            request=request,
            provider="openrouter",
            allow_preview_only=False,
            allow_attended_openrouter=True,
        )
        if limit is not None and estimate.max_cost > limit:
            raise click.ClickException(f"OpenRouter envelope ${estimate.max_cost:.4f} exceeds --limit ${limit:.2f}")
        _confirm_openrouter_spend(max_cost=estimate.max_cost, yes=yes)
        job_id = f"or-research-{uuid.uuid4().hex}"
        parent = open_parent_budget_transaction(
            surface="openrouter_attended_research",
            parent_ceiling_usd=estimate.max_cost,
            run_id=job_id,
        )
        spend_caps = resolve_spend_caps(provider="openrouter")
        per_job = estimate.max_cost if limit is None else min(estimate.max_cost, limit)
        try:
            reservation = reserve_research_cost(
                job_id=job_id,
                provider="openrouter",
                model=model,
                estimate=estimate,
                max_cost_per_job=per_job,
                max_daily_cost=spend_caps["daily"],
                max_weekly_cost=spend_caps["weekly"],
                max_monthly_cost=spend_caps["monthly"],
                request=request,
            )
        except ResearchCostBlocked as exc:
            raise click.ClickException(str(exc)) from exc
        require_unproxied_paid_transport()
        if not load_openrouter_api_key():
            refund_research_cost(reservation, provider_work_did_not_run=True)
            raise click.ClickException("OPENROUTER_API_KEY is not available")
        ResearchReservationStore().mark_provider_work_may_have_run(
            reservation.reservation_id,
            provider=reservation.provider,
            model=reservation.model,
            job_id=reservation.job_id,
            reserved_cost=reservation.estimated_cost,
            dispatch_binding_id=reservation.dispatch_binding_id,
            request_envelope_sha256=reservation.request_envelope_sha256,
        )
        try:
            result = _dispatch_openrouter_completion(
                model=model,
                query=query,
                max_tokens=request.max_output_tokens,
                prompt_max_price=capability.input_cost_per_1m,
                completion_max_price=capability.output_cost_per_1m,
            )
        except click.ClickException:
            settle_research_cost(
                reservation,
                actual_cost=None,
                source="openrouter_attended.failed",
                actual_cost_reported=False,
            )
            raise
        if result.cost_usd > reservation.estimated_cost:
            settle_research_cost(
                reservation,
                actual_cost=reservation.estimated_cost,
                tokens=result.completion_tokens,
                request_id=result.generation_id,
                source="openrouter_attended.over_hold",
            )
            raise click.ClickException(
                f"OpenRouter usage.cost ${result.cost_usd:.6f} exceeded the "
                f"${reservation.estimated_cost:.4f} hold; the hold was consumed"
            )
        settle_research_cost(
            reservation,
            actual_cost=result.cost_usd,
            tokens=result.completion_tokens,
            request_id=result.generation_id,
            source="openrouter_attended",
        )
        parent.close()
        _print_and_store(query=query, model=model, job_id=job_id, result=result)


def _print_and_store(*, query: str, model: str, job_id: str, result: OpenRouterCompletionResult) -> None:
    from deepr.config import load_config
    from deepr.utils.atomic_io import atomic_write_text

    print_header("OpenRouter attended research")
    print_key_value("Job ID", job_id)
    print_key_value("Model", result.model)
    print_key_value("Upstream", result.provider_name)
    print_key_value("Settled cost", f"${result.cost_usd:.6f}")
    print_key_value("Tokens", f"{result.prompt_tokens} in / {result.completion_tokens} out")
    console.print()
    console.print(result.content, markup=False)
    reports = Path(load_config()["results_dir"])
    reports.mkdir(parents=True, exist_ok=True)
    path = reports / f"{job_id}.md"
    atomic_write_text(
        path,
        f"# OpenRouter attended research\n\nQuery: {query}\nModel: {model}\n"
        f"Cost: ${result.cost_usd:.6f}\nGeneration: {result.generation_id}\n\n"
        f"{result.content}\n",
    )
    print_key_value("Report", str(path))


__all__ = ["run_attended_openrouter_research"]
