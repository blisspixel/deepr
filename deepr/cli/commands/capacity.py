"""`deepr capacity` - show research capacity sources (read-only, $0).

Surfaces what capacity is available - local hardware, plan-quota CLIs, metered
APIs - so the operator can see the owned/prepaid capacity that capacity-aware
routing drains before touching a metered API. Visibility only today: this
detects sources and never runs research or spends. Design:
docs/design/capacity-waterfall.md.
"""

from __future__ import annotations

import json as _json

import click

from deepr.backends.capacity import BackendKind, detect_capacity

_GROUP_ORDER = [
    (BackendKind.LOCAL, "Local (free at the margin)"),
    (BackendKind.PLAN_QUOTA, "Plan quota (prepaid - your subscriptions)"),
    (BackendKind.API_METERED, "Metered API (paid per call - last resort)"),
]


@click.command(name="capacity")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def capacity(json_output: bool):
    """Show available research capacity (local, plan quota, metered API).

    Capacity-aware routing (v2.16) drains owned and prepaid capacity before any
    metered API call. This command makes that capacity visible; it runs no
    research and spends nothing.
    """
    sources = detect_capacity()

    if json_output:
        click.echo(_json.dumps([s.to_dict() for s in sources], indent=2))
        return

    click.echo("Research capacity (used in order: local -> plan quota -> metered API)\n")
    for kind, heading in _GROUP_ORDER:
        group = [s for s in sources if s.kind == kind]
        if not group:
            continue
        click.echo(heading)
        for s in group:
            mark = "+" if s.available else "-"
            status = "available" if s.available else "not available"
            click.echo(f"  [{mark}] {s.name:24s} {status:14s} {s.marginal_cost:16s} {s.detail}")
        click.echo("")

    local_or_plan = [s for s in sources if s.kind in (BackendKind.LOCAL, BackendKind.PLAN_QUOTA) and s.available]
    if local_or_plan:
        names = ", ".join(s.name for s in local_or_plan)
        click.echo(f"Owned/prepaid capacity available: {names}")
    else:
        click.echo(
            "No owned/prepaid capacity detected. Install Ollama or a plan CLI to research without per-call cost."
        )
    click.echo("Note: capacity-aware routing is in progress (v2.16); research currently runs on metered API providers.")
