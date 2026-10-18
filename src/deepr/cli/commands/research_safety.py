"""CLI adapters for fail-closed research cost boundaries."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import NoReturn

import click

from deepr.cli.output import OperationResult, OutputContext, OutputFormatter
from deepr.core.costs import CostEstimate
from deepr.services.research_bounds import (
    ResearchRequestBoundsError,
    bounded_research_cost_estimate,
    require_metered_interface_accounting,
    require_research_parent_budget_accounting,
    require_research_storage_accounting,
)


class ResearchCLIError(click.ClickException):
    """A research refusal with a stable machine-readable code."""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.error_code = code


def _as_click_error(exc: ResearchRequestBoundsError) -> click.ClickException:
    return ResearchCLIError(f"{exc.code}: {exc}", exc.code)


def fail_research(
    output_context: OutputContext,
    error: str | Exception,
    *,
    error_code: str | None = None,
    category: str = "validation",
    formatter: OutputFormatter | None = None,
) -> NoReturn:
    """Finish one refused CLI operation without reporting successful execution."""
    result = OperationResult(
        success=False,
        duration_seconds=0.0,
        cost_usd=0.0,
        error=str(error),
        error_code=error_code or getattr(error, "error_code", None) or getattr(error, "code", "RESEARCH_REFUSED"),
        category=category,
        retryable=False,
    )
    (formatter or OutputFormatter(output_context)).complete(result, error_to_stderr=True)
    raise SystemExit(1)


def research_failure_boundary(function):
    """Adapt known command refusals to the existing CLI operation envelope."""

    @wraps(function)
    def wrapped(*args, **kwargs):
        from deepr.experts.research_cost_gate import ResearchCostBlocked
        from deepr.routing.auto_mode import AutoRoutingUnavailable

        output_context = kwargs["output_context"]
        try:
            return function(*args, **kwargs)
        except click.Abort:
            fail_research(output_context, "Research cancelled.", error_code="CANCELLED")
        except click.UsageError as exc:
            fail_research(output_context, exc, error_code="INVALID_INPUT")
        except (click.ClickException, ResearchRequestBoundsError, ResearchCostBlocked, AutoRoutingUnavailable) as exc:
            fail_research(output_context, exc)

    return wrapped


def require_research_credential(provider: str, output_context: OutputContext) -> None:
    """Check presence only; this is neither credential validity nor spend authority."""
    from deepr.cli.commands.keys import PROVIDERS
    from deepr.cli.commands.provider_factory import credential_presence

    present, name = credential_presence(provider)
    if not present:
        setup = (
            f"'deepr keys set {provider}' or the environment" if provider in PROVIDERS else ".env or the environment"
        )
        fail_research(
            output_context,
            f"No credential found for provider '{provider}'. Set {name} using {setup}. "
            "Use --preview to inspect the route without a key.",
            error_code="MISSING_API_KEY",
            category="auth",
        )


def require_budget_confirmation(
    yes: bool,
    estimated_cost: float,
    output_context: OutputContext,
    formatter: OutputFormatter,
    approval_check: Callable[[bool, float, OutputContext], bool],
) -> None:
    """Finish the operation on unconfirmed cost, including an aborted prompt."""
    try:
        if approval_check(yes, estimated_cost, output_context):
            return
    except click.Abort:
        fail_research(output_context, "Research cancelled.", error_code="CANCELLED", formatter=formatter)
    fail_research(
        output_context,
        f"Budget gate: estimated ${estimated_cost:.2f} is not approved. "
        "-y cannot consent past the gate. Inspect 'deepr budget show', "
        "run interactively with --verbose to confirm, or use --preview without spending.",
        error_code="BUDGET_NOT_APPROVED",
        category="budget",
        formatter=formatter,
    )


def require_storage() -> None:
    """Require a fully priced provider storage lifecycle."""
    try:
        require_research_storage_accounting()
    except ResearchRequestBoundsError as exc:
        raise _as_click_error(exc) from exc


def require_parent_budget(operation: str) -> None:
    """Require one durable parent reservation for a multi-call operation."""
    try:
        require_research_parent_budget_accounting(operation)
    except ResearchRequestBoundsError as exc:
        raise _as_click_error(exc) from exc


def require_metered_interface(operation: str) -> None:
    """Require durable admission and settlement for a direct metered interface."""
    try:
        require_metered_interface_accounting(operation)
    except ResearchRequestBoundsError as exc:
        raise _as_click_error(exc) from exc


def bounded_admission_estimate(
    *,
    query: str,
    provider: str,
    model: str,
    no_web: bool,
    no_code: bool,
    allow_preview_only: bool = False,
) -> CostEstimate:
    """Build the exact finite request envelope used by dispatch admission."""
    from deepr.cli.commands.run_submission import build_bounded_cli_request

    request = build_bounded_cli_request(
        query=query,
        model=model,
        no_web=no_web,
        no_code=no_code,
    )
    try:
        return bounded_research_cost_estimate(
            request=request,
            provider=provider,
            allow_preview_only=allow_preview_only,
        )
    except ResearchRequestBoundsError as exc:
        raise _as_click_error(exc) from exc


def require_dispatchable_admission(query: str, provider: str, model: str, no_web: bool, no_code: bool) -> None:
    """Fail before side effects when an exact route is preview-only."""
    bounded_admission_estimate(query=query, provider=provider, model=model, no_web=no_web, no_code=no_code)


def print_explicit_research_preview(
    query: str,
    provider: str,
    model: str,
    upload: tuple,
    no_web: bool,
    no_code: bool,
    output_context: object,
    requested_no_web: bool = False,
) -> None:
    """Print a write-free preview for an explicit provider/model research run."""
    del upload
    from deepr.cli.colors import console
    from deepr.cli.output import OutputMode

    estimate = bounded_admission_estimate(
        query=query,
        provider=provider,
        model=model,
        no_web=no_web,
        no_code=no_code,
        allow_preview_only=True,
    )
    from deepr.cli.commands.research_support import research_tool_posture

    tools = research_tool_posture(provider, model, no_web=no_web, no_code=no_code, requested_no_web=requested_no_web)
    mode = getattr(output_context, "mode", None)
    if mode == OutputMode.JSON:
        import json

        payload = {
            "preview": True,
            "executed": False,
            "provider": provider,
            "model": model,
            "cost_estimate": {
                "min": round(estimate.min_cost, 6),
                "expected": round(estimate.expected_cost, 6),
                "max": round(estimate.max_cost, 6),
            },
            "reasoning": estimate.reasoning,
            "tools": tools,
        }
        click.echo(json.dumps(payload, indent=2))
        return
    console.print()
    console.print("[bold]Research Preview[/bold]")
    console.print(f"[dim]{'─' * 40}[/dim]")
    console.print(f"  Provider:   {provider}")
    console.print(f"  Model:      {model}")
    console.print(f"  Web search: {'enabled' if not no_web else 'disabled'}")
    console.print(f"    {tools['web_search_reason']}")
    if no_web:
        console.print("    No live web sources will be checked; answers use model knowledge and supplied context.")
    console.print(f"  Code tool:  {'enabled' if not no_code else 'disabled'}")
    console.print(
        f"  Est. cost:  ${estimate.min_cost:.4f} - ${estimate.max_cost:.4f} (expected ${estimate.expected_cost:.4f})"
    )
    if estimate.reasoning:
        console.print(f"  [dim]{estimate.reasoning}[/dim]")
    console.print("[yellow]  (preview only - no provider call, no spend)[/yellow]")
    console.print()


__all__ = [
    "bounded_admission_estimate",
    "print_explicit_research_preview",
    "require_dispatchable_admission",
    "require_metered_interface",
    "require_parent_budget",
    "require_storage",
]
