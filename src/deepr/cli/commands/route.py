"""`deepr route explain` - inspect how a query would route before dispatching.

A $0, read-only, no-model command: it shows which experts a consult would fan out
to (by the deterministic keyword-overlap selection router) and the non-probing
capacity outlook (whether the next maintenance run is $0/prepaid or metered) so an
operator can see the route and its spend posture before spending anything.
"""

from __future__ import annotations

import json as _json
import sys

import click
from rich.markup import escape

from deepr.cli.colors import console, print_capacity_outlook, print_error, print_header


@click.group(name="route")
def route() -> None:
    """Inspect deterministic routing decisions before dispatching work."""


@route.command(name="explain")
@click.argument("query")
@click.option(
    "--max-experts",
    type=click.IntRange(min=1),
    default=3,
    show_default=True,
    help="Experts a consult would fan out to",
)
@click.option(
    "--top",
    "top_n",
    type=click.IntRange(min=1),
    default=5,
    show_default=True,
    help="Ranked candidate experts to show",
)
@click.option("--json", "json_output", is_flag=True, help="Emit the route explanation as JSON")
def explain(query: str, max_experts: int, top_n: int, json_output: bool) -> None:
    """Show how QUERY would route (experts + capacity posture) at $0, no model call.

    The keyword-overlap score is a high-recall selection router, not a judgment of
    which expert is right or whether the answer will be correct.

    EXAMPLES:
      deepr route explain "cloud security threat modeling"
      deepr route explain "kubernetes autoscaling" --json
    """
    from deepr.experts.route_explanation import build_route_explanation

    try:
        payload = build_route_explanation(query, max_experts=max_experts, top_n=top_n)
    except Exception as exc:  # a read-only explainer must fail with a clean message, not a traceback
        print_error(f"Could not build route explanation: {escape(str(exc))}")
        sys.exit(1)

    if json_output:
        click.echo(_json.dumps(payload, indent=2))
        return

    # The query is operator input; escape it before the markup-enabled header so a
    # bracketed query never crashes or is swallowed as Rich markup.
    print_header(f"Route explanation: {escape(query)}")
    routing = payload["expert_routing"]
    console.print(
        f"[dim]{routing['expert_count']} expert(s) registered; keyword-overlap selection router "
        f"(a routing signal, not a quality or authority verdict).[/dim]"
    )
    would = routing["would_consult"]
    if would:
        console.print(f"Would consult (max {routing['max_experts']}): [bold]{escape(', '.join(would))}[/bold]")
    else:
        console.print("Would consult: [dim]none (no experts registered)[/dim]")
    for cand in routing["candidates"]:
        mark = "*" if cand["would_consult"] else " "
        terms = escape(", ".join(cand["matched_terms"])) if cand["matched_terms"] else "no overlap"
        console.print(
            f"  [{mark}] [bold]{escape(cand['name'])}[/bold] [dim](overlap {cand['overlap_score']}: {terms})[/dim]"
        )

    console.print()
    print_capacity_outlook(payload.get("capacity_outlook") or {})
    console.print(f"[dim]Backend fallback order: {' -> '.join(payload['backend_fallback_order'])}[/dim]")
