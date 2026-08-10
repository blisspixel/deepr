"""CLI: `deepr expert health` - which experts are worth consulting.

Forty experts is not inspectable by opening forty directories. This reads what
is already on disk, grades each one for triage, and pairs every grade with the
single most useful next action, because a letter on its own tells nobody what
to do about it.

$0. No model call, no network.
"""

from __future__ import annotations

import json

import click

from deepr.cli.colors import console, print_header, print_key_value
from deepr.cli.commands.semantic.experts import expert
from deepr.experts.expert_health import (
    ExpertHealth,
    assess_expert,
    fleet_summary,
    last_consulted_days,
)
from deepr.experts.paths import canonical_expert_dir

_GRADE_COLOR = {"S": "bright_green", "A": "green", "B": "cyan", "C": "yellow", "D": "yellow", "F": "red"}
_GRADE_ORDER = {"F": 0, "D": 1, "C": 2, "B": 3, "A": 4, "S": 5}


def _belief_count(name: str) -> int:
    try:
        from deepr.experts.beliefs import BeliefStore

        return len(BeliefStore(name, read_only=True).beliefs)
    except Exception:
        return 0


def collect_fleet(names: list[str]) -> list[ExpertHealth]:
    """Assess every named expert from what is on disk.

    Consult recency comes from one scan of the shared trace log rather than
    per expert, because it is a single append-only file and forty experts
    would otherwise read it forty times.
    """
    consulted = last_consulted_days()
    return [
        assess_expert(
            n,
            canonical_expert_dir(n),
            beliefs=_belief_count(n),
            consulted_days_ago=consulted.get(n, -1),
        )
        for n in names
    ]


def _render_row(health: ExpertHealth) -> None:
    color = _GRADE_COLOR.get(health.grade, "white")
    depth = f"{health.effective_origins:.1f}" if health.sources else "-"
    console.print(
        f"  [{color}]{health.grade}[/{color}]  {health.name[:38]:38s} "
        f"src {health.sources:>3}  origins {depth:>4}  "
        f"findings {health.findings:>3}  positions {health.positions:>2}"
    )


@expert.command(name="health")
@click.option("--all", "show_all", is_flag=True, help="Include experts that are already consultable")
@click.option("--json", "as_json", is_flag=True, help="Emit the fleet health JSON")
def expert_health_cmd(show_all: bool, as_json: bool) -> None:
    """Grade every expert and say what each one needs next ($0).

    A grade is triage, not a verdict. Depth is counted by independent origin
    rather than document, because thirty pages from one publisher is one
    publisher's authority. An expert with no brief caps at C however large its
    corpus: it has not landed anywhere, so it is a search index.

    EXAMPLES:

      deepr expert health              deepr expert health --all --json
    """
    from deepr.experts.profile import ExpertStore

    names = [p.name for p in ExpertStore().list_all()]
    # Thinnest first within a grade, matching what the heading promises. The
    # sort was descending, so the experts most in need of sources sat at the
    # bottom of a list whose whole purpose is showing what needs attention.
    fleet = sorted(collect_fleet(names), key=lambda h: (_GRADE_ORDER.get(h.grade, 9), h.effective_origins, h.name))
    summary = fleet_summary(fleet)

    if as_json:
        click.echo(
            json.dumps(
                {"summary": summary, "experts": [h.to_dict() for h in fleet], "cost_usd": 0.0},
                indent=2,
                sort_keys=True,
            )
        )
        return

    print_header("Expert fleet health")
    print_key_value("Experts", str(summary["experts"]))
    print_key_value("Consultable", f"{summary['consultable']} (formed a view, resting on checkable findings)")
    print_key_value("Never studied", str(summary["never_studied"]))
    print_key_value("Grades", ", ".join(f"{g}:{n}" for g, n in summary["by_grade"].items()))

    needs_work = [h for h in fleet if not h.is_consultable]
    shown = fleet if show_all else needs_work
    if not shown:
        console.print("\n[green]Every expert is consultable.[/green]")
        return

    heading = "Every expert" if show_all else "Needs work"
    console.print(f"\n[bold]{heading}[/bold]  (grade, then thinnest first)\n")
    for health in shown:
        _render_row(health)
        console.print(f"      [dim]{health.next_action}[/dim]")

    if not show_all and len(needs_work) < len(fleet):
        console.print(
            f"\n[dim]{len(fleet) - len(needs_work)} consultable expert(s) hidden. Use --all to see them.[/dim]"
        )
    console.print("\n[dim]A grade is triage, not a verdict. Depth is independent origins, not documents.[/dim]")
