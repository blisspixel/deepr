"""`deepr expert consult` - consult a team of experts as one knowledge transaction.

Extracted from experts.py (file-size cap). Routes a question to the relevant
experts (or an explicit set), gathers bounded perspectives, and synthesizes one
calibrated answer with agreements/disagreements - the single, bounded "knowledge
transaction" in docs/design/agentic-harness-boundary.md. This is the first-class
verb so any agentic harness can consult Deepr's expert team via one command (and
the matching MCP tool) instead of scripting the council.
"""

from __future__ import annotations

import asyncio
import json as _json
import sys
from typing import Any

import click

from deepr.cli.colors import console, print_error, print_warning
from deepr.cli.commands.semantic.experts import expert

# Shared core (also used by the deepr_consult_experts MCP tool). Re-exported so
# existing importers/tests keep working.
from deepr.experts.consult import build_consult_payload, run_consult

__all__ = ["build_consult_payload", "expert_consult", "run_consult"]


def _render(payload: dict[str, Any]) -> None:
    names = payload["experts_consulted"]
    console.print(f"[bold]Consulted {len(names)} expert(s):[/bold] {', '.join(names) or '(none)'}")
    for p in payload["perspectives"]:
        console.print(f"\n[bold]{p['expert']}[/bold] [dim](conf {p['confidence']:.2f})[/dim]")
        console.print(f"  {p['response'][:600]}")
    console.print("\n[bold]Synthesis[/bold]")
    console.print(payload["answer"][:1400] or "  [dim](no synthesis)[/dim]")
    for label, key in (("Agreements", "agreements"), ("Disagreements", "disagreements")):
        if payload[key]:
            console.print(f"\n[bold]{label}[/bold]")
            for item in payload[key][:6]:
                console.print(f"  - {item}")
    console.print(f"\n[dim]Cost: ${payload['cost_usd']:.4f}[/dim]")


@expert.command(name="consult")
@click.argument("question")
@click.option(
    "--expert",
    "-e",
    "experts",
    multiple=True,
    help="Expert to include (repeatable). Omit to auto-select relevant experts.",
)
@click.option("--max-experts", default=3, show_default=True, help="Max experts when auto-selecting (capped at 5).")
@click.option("--budget", "-b", default=2.0, show_default=True, help="USD ceiling for this consultation.")
@click.option("--json", "json_output", is_flag=True, help="Emit the versioned consult artifact (deepr-consult-v1).")
@click.option("-y", "--yes", is_flag=True, help="Skip the spend confirmation.")
def expert_consult(question, experts, max_experts, budget, json_output, yes):
    """Consult a team of experts and synthesize one calibrated answer.

    One bounded knowledge transaction: route to the relevant experts (or the ones
    you name with -e), gather their perspectives, and synthesize an answer with
    agreements and dissent. Deepr recommends; your harness decides and enacts.

    EXAMPLES:
      deepr expert consult "How should we harden absorption provenance?"
      deepr expert consult "Cost vs quality tradeoff?" -e "AI Cost Optimization" -e "LLM Evaluation and Calibration"
      deepr expert consult "What changed in MCP?" --json
    """
    if budget <= 0:
        print_error("--budget must be positive.")
        sys.exit(2)
    if not yes and not json_output and not click.confirm(f"Consult experts (budget ${budget:.2f})?", default=True):
        print_warning("Cancelled.")
        return

    try:
        result = asyncio.run(run_consult(question, list(experts), max_experts, budget))
    except Exception as e:  # surface the failure honestly; never a silent empty result
        print_error(f"Consultation failed: {e}")
        sys.exit(1)

    payload = build_consult_payload(question, result)
    if json_output:
        click.echo(_json.dumps(payload, indent=2))
    else:
        _render(payload)

    if not payload["experts_consulted"]:
        if not json_output:
            print_warning("No experts were consulted - create experts first or name them with -e.")
        sys.exit(2)
