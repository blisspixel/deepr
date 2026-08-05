"""CLI: structural expert quality scorecard and improve plan ($0)."""

from __future__ import annotations

import json
import sys
from typing import Any

import click

from deepr.cli.colors import console, print_header, print_key_value
from deepr.cli.commands.semantic.experts import expert


@expert.command(name="council-plan")
@click.argument("goal", required=False, default=None)
@click.option(
    "--from-file",
    "from_file",
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    default=None,
    help="Read goal/project text from a file (README, roadmap, etc.)",
)
@click.option(
    "--roles",
    "role_count",
    type=click.IntRange(4, 8),
    default=5,
    show_default=True,
    help="Number of council roles (diversity gate needs at least 4 axes)",
)
@click.option(
    "--local",
    is_flag=True,
    help="Compose concrete roles with local Ollama ($0 API); else structural scaffold",
)
@click.option("--local-model", default=None, help="Ollama model override for --local composition")
@click.option("--json", "as_json", is_flag=True, help="Emit deepr-expert-council-plan-v1 JSON")
@click.option("--output", type=click.Path(dir_okay=False, path_type=str), default=None)
def expert_council_plan(
    goal: str | None,
    from_file: str | None,
    role_count: int,
    local: bool,
    local_model: str | None,
    as_json: bool,
    output: str | None,
) -> None:
    """Propose a diverse expert council for a goal or project text.

    Diversity is multi-axis (domain, adversary, ops, standards, extreme user,
    rigor, economics, history) - not N clones of the same domain expert.
    Emits make + deepen-plan commands and a challenge consult prompt.
    Does not create experts or run research.

    EXAMPLES:
      deepr expert council-plan --from-file README.md --local
      deepr expert council-plan "Off-grid mesh + intent-driven K8s" --local
      deepr expert council-plan --from-file docs/roadmap.md
    """
    import asyncio
    from pathlib import Path

    from deepr.experts.council_plan import (
        build_scaffold_council_plan,
        compose_council_with_local_model,
    )
    from deepr.experts.profile import ExpertStore

    text = ""
    if from_file:
        text = Path(from_file).read_text(encoding="utf-8", errors="replace")
    if goal:
        text = f"{goal.strip()}\n\n{text}".strip() if text else goal.strip()
    if not text:
        click.echo("Error: provide GOAL text and/or --from-file.", err=True)
        sys.exit(2)

    existing = [p.name for p in ExpertStore().list_all()]
    if local:
        plan = asyncio.run(
            compose_council_with_local_model(
                text,
                role_count=role_count,
                model=local_model,
                existing_experts=existing,
            )
        )
    else:
        plan = build_scaffold_council_plan(
            text,
            role_count=role_count,
            existing_experts=existing,
        )

    body = json.dumps(plan.to_dict(), indent=2, sort_keys=True) if as_json else plan.to_markdown()
    if output:
        Path(output).write_text(body, encoding="utf-8")
        click.echo(f"Wrote council plan: {output}")
        return
    click.echo(body, nl=not as_json)
    if not plan.diversity_ok:
        sys.exit(2)


@expert.command(name="deepen-plan")
@click.argument("name")
@click.option(
    "--query",
    default=None,
    help="Research focus override (default: expert domain description)",
)
@click.option("--json", "as_json", is_flag=True, help="Emit deepr-expert-deepen-plan-v1 JSON")
@click.option("--output", type=click.Path(dir_okay=False, path_type=str), default=None)
def expert_deepen_plan(name: str, query: str | None, as_json: bool, output: str | None) -> None:
    """Emit a Distillr/Learny deepen recipe for NAME ($0, no network, no absorb).

    Does not run Distill or write beliefs. Use after ``expert quality`` shows
    high circularity or low multi-source share. Prefer Distill
    ``--cost-mode no-metered`` for $0 API analysis on local Ollama.

    EXAMPLES:
      deepr expert deepen-plan "Meshtastic LoRa Mesh Automation"
      deepr expert deepen-plan "Python Expert" --query "Python 3.13 packaging"
    """
    from pathlib import Path

    from deepr.experts.deepen_plan import build_deepen_plan
    from deepr.experts.profile import ExpertStore

    store = ExpertStore()
    profile = store.load(name)
    if not profile:
        click.echo(f"Error: Expert not found: {name}", err=True)
        sys.exit(2)

    plan = build_deepen_plan(
        expert_name=profile.name,
        domain=profile.domain or profile.description or profile.name,
        query=query,
    )
    if as_json:
        text = json.dumps(plan.to_dict(), indent=2, sort_keys=True)
    else:
        text = plan.to_markdown()
    if output:
        Path(output).write_text(text, encoding="utf-8")
        click.echo(f"Wrote deepen plan: {output}")
        return
    click.echo(text, nl=not as_json)


@expert.command(name="quality")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True, help="Emit deepr-expert-quality-v1 JSON")
def expert_quality(name: str, as_json: bool) -> None:
    """Score structural provenance quality for NAME at $0.

    Measures trust mix, multi-source share, project-intent circularity risk,
    effective confidence, and learning-loop evidence. Does **not** claim
    semantic excellence - use for research→plan→improve loops and coding-agent
    inventory honesty.

    EXAMPLES:
      deepr expert quality "Meshtastic LoRa Mesh Automation"
      deepr expert quality "Meshtastic LoRa Mesh Automation" --json
    """
    from deepr.experts.beliefs import BeliefStore
    from deepr.experts.profile import ExpertStore
    from deepr.experts.quality_scorecard import build_quality_scorecard

    store = ExpertStore()
    profile = store.load(name)
    if not profile:
        click.echo(f"Error: Expert not found: {name}", err=True)
        sys.exit(2)

    manifest = profile.get_manifest()
    beliefs = list(BeliefStore(name).beliefs.values())
    verified_loops = 0
    try:
        from deepr.experts.loop_runs import ExpertLoopRunStore
        from deepr.experts.next_actions import _learning_evidence

        learning = _learning_evidence(ExpertLoopRunStore(name).list_runs(limit=50))
        verified_loops = int(learning.get("verified_improvement_count", 0) or 0)
    except Exception:
        verified_loops = 0

    card = build_quality_scorecard(
        expert_name=profile.name,
        domain=profile.domain or manifest.domain or profile.name,
        beliefs=beliefs,
        open_gap_count=int(getattr(manifest, "open_gap_count", 0) or 0),
        verified_learning_loops=verified_loops,
    )

    if as_json:
        click.echo(json.dumps(card.to_dict(), indent=2, sort_keys=True))
        return

    _render_quality_scorecard(card)


def _render_quality_scorecard(card: Any) -> None:
    print_header(f"Expert quality: {card.expert_name}")
    print_key_value("Grade (structural)", card.grade)
    print_key_value("Stage hint", card.stage_hint)
    print_key_value("Claims", str(card.claim_count))
    print_key_value("Trust mix", str(card.trust_mix))
    print_key_value("Secondary+ share", f"{card.secondary_or_better_share:.2f}")
    print_key_value(
        "Multi-source share",
        f"{card.multi_source_share:.2f} ({card.multi_source_count} claims)",
    )
    print_key_value("Distinct origins", str(card.distinct_origin_count))
    print_key_value("Circularity risk", f"{card.circularity_risk:.2f} ({card.circular_claim_count} claims)")
    print_key_value(
        "Effective confidence",
        f"min={card.effective_confidence.get('min')} avg={card.effective_confidence.get('avg')} "
        f"max={card.effective_confidence.get('max')}",
    )
    print_key_value("Open gaps", str(card.open_gap_count))
    print_key_value("Verified learning loops", str(card.verified_learning_loops))

    if card.blockers:
        console.print("\n[bold red]Blockers[/bold red]")
        for b in card.blockers:
            console.print(f"  - {b}")
    if card.strengths:
        console.print("\n[bold green]Strengths[/bold green]")
        for s in card.strengths:
            console.print(f"  - {s}")
    if card.next_actions:
        console.print("\n[bold cyan]Next improve actions[/bold cyan]")
        for action in card.next_actions:
            console.print(f"  - {action['title']}: {action['reason']}")
            for argv in action.get("command_argv") or []:
                console.print(f"      [dim]{' '.join(argv)}[/dim]")

    console.print(
        "\n[dim]Structural only. Exceptional meaning requires primary multi-source "
        "corpus + challenge consults + measured learning loops. See "
        "docs/design/exceptional-expert-quality.md[/dim]"
    )


@expert.command(name="improve")
@click.argument("name")
@click.option(
    "--local",
    is_flag=True,
    help="Prefer $0 local capacity for any execute path (recommended)",
)
@click.option(
    "--execute",
    is_flag=True,
    help=(
        "Run the non-mutating improve steps: discover-gaps and route-gaps --dry-run. "
        "discover-gaps is metered-gated and fails closed while paid dispatch is frozen."
    ),
)
@click.option("--json", "as_json", is_flag=True, help="Emit scorecard + plan JSON")
def expert_improve(name: str, local: bool, execute: bool, as_json: bool) -> None:
    """Research → plan → improve loop for one expert (structural orchestration).

    Always prints a quality scorecard and an improve plan. With --execute, runs
    only non-mutating steps: discover-gaps and route-gaps --dry-run.

    Note: discover-gaps is metered-gated and takes no --local, so while paid
    dispatch is frozen that step fails closed rather than running. This command
    has no --api option; nothing here can authorize spend.

    Absorb of primary docs remains an explicit operator absorb command (files
    and trust-class must be chosen deliberately).

    EXAMPLES:
      deepr expert improve "Meshtastic LoRa Mesh Automation" --local
      deepr expert improve "Meshtastic LoRa Mesh Automation" --local --execute
    """
    from deepr.experts.beliefs import BeliefStore
    from deepr.experts.profile import ExpertStore
    from deepr.experts.quality_scorecard import build_quality_scorecard

    store = ExpertStore()
    profile = store.load(name)
    if not profile:
        click.echo(f"Error: Expert not found: {name}", err=True)
        sys.exit(2)

    manifest = profile.get_manifest()
    beliefs = list(BeliefStore(name).beliefs.values())
    before = build_quality_scorecard(
        expert_name=profile.name,
        domain=profile.domain or manifest.domain or profile.name,
        beliefs=beliefs,
        open_gap_count=int(getattr(manifest, "open_gap_count", 0) or 0),
        verified_learning_loops=0,
    )

    executed: list[dict[str, Any]] = []
    if execute:
        # Discover gaps mutates gap inventory - local/structural, $0.
        from click.testing import CliRunner

        from deepr.cli.main import cli

        runner = CliRunner()
        gap_result = runner.invoke(cli, ["expert", "discover-gaps", name])
        executed.append(
            {
                "step": "discover-gaps",
                "ok": gap_result.exit_code == 0,
                "exit_code": gap_result.exit_code,
                "output_tail": (gap_result.output or "")[-1500:],
            }
        )
        route_argv = ["expert", "route-gaps", name, "--execute", "--dry-run"]
        if local:
            route_argv.append("--local")
        route_result = runner.invoke(cli, route_argv)
        executed.append(
            {
                "step": "route-gaps-dry-run",
                "ok": route_result.exit_code == 0,
                "exit_code": route_result.exit_code,
                "output_tail": (route_result.output or "")[-1500:],
            }
        )
        # Refresh after gap discovery
        profile = store.load(name) or profile
        manifest = profile.get_manifest()
        beliefs = list(BeliefStore(name).beliefs.values())

    after = build_quality_scorecard(
        expert_name=profile.name,
        domain=profile.domain or manifest.domain or profile.name,
        beliefs=beliefs,
        open_gap_count=int(getattr(manifest, "open_gap_count", 0) or 0),
        verified_learning_loops=0,
    )

    plan = {
        "schema_version": "deepr-expert-improve-plan-v1",
        "kind": "deepr.expert.improve_plan",
        "expert": name,
        "local": local,
        "execute": execute,
        "before": before.to_dict(),
        "after": after.to_dict() if execute else None,
        "executed": executed,
        "operator_required": [
            {
                "step": "deepen_plan_distill",
                "why": "Build multi-source Distill corpus (local no-metered) then absorb secondary.",
                "example": f'deepr expert deepen-plan "{name}"',
            },
            {
                "step": "absorb_independent_secondary_docs",
                "why": "Absorb Distill library MD or official docs as secondary trust.",
                "example": (
                    f'deepr expert absorb "{name}" --file <official-or-distill-insight.md> '
                    f"--local --trust-class secondary -y"
                ),
            },
            {
                "step": "separate_project_stance",
                "why": "Project intent should be primary stance on hybrid experts, not sole domain truth.",
                "example": (f'deepr expert absorb "{name}" --file <intent.md> --local --trust-class primary -y'),
            },
            {
                "step": "regenerate_wiki_digest",
                "why": "Derived wiki sections refresh after absorb.",
                "example": f'deepr expert digest "{name}"',
            },
            {
                "step": "challenge_consult",
                "why": "Ask for dissent vs current design after multi-source absorb.",
                "example": (
                    f'deepr expert consult "Challenge our design: what did we get wrong?" '
                    f'-e "{name}" --local --budget 0 -y'
                ),
            },
        ],
        "cost_usd": 0.0,
        "limitations": [
            "Improve orchestrates structural steps; it does not auto-download the web.",
            "Exceptional quality still requires Distill/Learny corpus depth and human review.",
            "See docs/design/living-expert-research-stack.md and docs/plans/living-expert-research-stack.md",
        ],
    }

    if as_json:
        click.echo(json.dumps(plan, indent=2, sort_keys=True, default=str))
        return

    print_header(f"Improve plan: {name}")
    print_key_value("Before grade", before.grade)
    print_key_value("Circularity risk", f"{before.circularity_risk:.2f}")
    print_key_value("Secondary+ share", f"{before.secondary_or_better_share:.2f}")
    print_key_value("Multi-source share", f"{before.multi_source_share:.2f}")
    if execute:
        print_key_value("After grade", after.grade)
        print_key_value("After open gaps", str(after.open_gap_count))
        for step in executed:
            status = "ok" if step["ok"] else f"failed ({step['exit_code']})"
            console.print(f"  executed {step['step']}: {status}")

    console.print("\n[bold]Blockers[/bold]")
    for b in before.blockers or ["(none)"]:
        console.print(f"  - {b}")

    console.print("\n[bold]Operator-required (not auto-run)[/bold]")
    for step in plan["operator_required"]:
        console.print(f"  - {step['step']}: {step['why']}")
        console.print(f"      [dim]{step['example']}[/dim]")

    console.print(
        '\n[dim]Deepen corpus: deepr expert deepen-plan "'
        f'{name}"  |  designs: docs/design/living-expert-research-stack.md, '
        "docs/plans/living-expert-research-stack.md[/dim]"
    )
