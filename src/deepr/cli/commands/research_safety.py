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
        return bounded_research_cost_estimate(request=request, provider=provider)
    except ResearchRequestBoundsError as exc:
        raise _as_click_error(exc) from exc


__all__ = [
    "bounded_admission_estimate",
    "require_metered_interface",
    "require_parent_budget",
    "require_storage",
]
