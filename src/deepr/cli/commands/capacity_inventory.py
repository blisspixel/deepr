"""Human-readable rendering for the read-only capacity inventory."""

from __future__ import annotations

from collections.abc import Iterable

import click

from deepr.backends.capacity import BackendKind, CapacitySource
from deepr.backends.plan_quota.adapters import get_adapter_by_executable

GROUP_ORDER = (
    (BackendKind.LOCAL, "Local runtime (detection only)"),
    (BackendKind.PLAN_QUOTA, "Plan CLIs (installation only)"),
    (BackendKind.API_METERED, "Metered API credentials (configuration only)"),
)


def print_sources(sources: Iterable[CapacitySource]) -> None:
    """Render source evidence without converting presence into eligibility."""
    inventory = list(sources)
    click.echo("Capacity sources detected (execution eligibility is workflow-specific)\n")
    for kind, heading in GROUP_ORDER:
        group = [source for source in inventory if source.kind == kind]
        if not group:
            continue
        click.echo(heading)
        for source in group:
            mark = "+" if source.available else "-"
            present, absent = {
                BackendKind.LOCAL: ("detected", "not detected"),
                BackendKind.PLAN_QUOTA: ("installed", "not installed"),
                BackendKind.API_METERED: ("configured", "not configured"),
            }[kind]
            status = present if source.available else absent
            click.echo(f"  [{mark}] {source.name:24s} {status:14s} {source.marginal_cost:16s} {source.detail}")
        click.echo("")

    click.echo("Inventory only: detection, installation, or credential presence does not prove execution.")
    available_kinds = {source.kind for source in inventory if source.available}
    if BackendKind.LOCAL in available_kinds:
        click.echo("Local: run `deepr capacity next --task-class sync` for a safe maintenance action.")
    plan_sources = [source for source in inventory if source.available and source.kind == BackendKind.PLAN_QUOTA]
    if any(get_adapter_by_executable(source.backend_id) for source in plan_sources):
        click.echo("Plan: run `deepr capacity fleet` to inspect adapter safety and blockers.")
    unadapted = [source.name for source in plan_sources if not get_adapter_by_executable(source.backend_id)]
    if unadapted:
        click.echo(f"Inventory only, no registered adapter: {', '.join(unadapted)}.")
    if BackendKind.API_METERED in available_kinds:
        click.echo('API: preview an exact request with `deepr research "your question" --auto --preview`.')
    if not available_kinds:
        click.echo("No source is currently present. Run `deepr init` to review setup options.")
