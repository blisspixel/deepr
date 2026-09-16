"""CLI adapters for fail-closed research cost boundaries."""

from __future__ import annotations

import click

from deepr.core.costs import CostEstimate
from deepr.services.research_bounds import (
    ResearchRequestBoundsError,
    bounded_research_cost_estimate,
    require_metered_interface_accounting,
    require_research_parent_budget_accounting,
    require_research_storage_accounting,
)


def _as_click_error(exc: ResearchRequestBoundsError) -> click.ClickException:
    return click.ClickException(f"{exc.code}: {exc}")


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
            "tools": {
                "web_search": not no_web,
                "code_interpreter": not no_code,
            },
        }
        click.echo(json.dumps(payload, indent=2))
        return
    console.print()
    console.print("[bold]Research Preview[/bold]")
    console.print(f"[dim]{'─' * 40}[/dim]")
    console.print(f"  Provider:   {provider}")
    console.print(f"  Model:      {model}")
    console.print(f"  Web search: {'enabled' if not no_web else 'disabled'}")
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
