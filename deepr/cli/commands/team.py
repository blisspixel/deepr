"""Team commands - dynamic dream team research."""

import click
import asyncio
from typing import Optional
from deepr.branding import print_section_header


@click.group()
def team():
    """Assemble dynamic research teams with diverse perspectives."""
    pass


@team.command()
@click.argument("question")
@click.option("--team-size", "-n", default=5, type=click.IntRange(3, 8),
              help="Number of team members (3-8)")
@click.option("--context", "-c", default=None,
              help="Additional context for research")
@click.option("--company", default=None,
              help="Company name to research for grounded personas (e.g., 'Anthropic', 'OpenAI')")
@click.option("--model", "-m", default="o4-mini-deep-research",
              type=click.Choice(["o4-mini-deep-research", "o3-deep-research"]),
              help="Deep research model for execution")
@click.option("--yes", "-y", is_flag=True,
              help="Skip confirmation and execute immediately")
def analyze(question: str, team_size: int, context: Optional[str], company: Optional[str], model: str, yes: bool):
    """
    Dynamically assemble optimal research team for your question.

    GPT-5 determines what perspectives this question needs, then each team
    member researches independently from their role. Final synthesis shows
    where they agree, where they conflict, and makes balanced recommendation.

    Examples:
        deepr team analyze "Should we pivot to enterprise?"
        deepr team analyze "How do we compete with Notion?" --team-size 6
        deepr team analyze "Future of AI coding tools?" --context "$(cat context.txt)"
        deepr team analyze "What's Anthropic's AI strategy?" --company "Anthropic"
    """
    print_section_header("Dynamic Dream Team Research")

    click.echo(f"\nQuestion: {question}")
    if context:
        click.echo(f"Context: {context[:100]}..." if len(context) > 100 else f"Context: {context}")
    if company:
        click.echo(f"Company: {company} (will research leadership for grounded personas)")
    click.echo(f"Team size: {team_size} members")
    click.echo(f"Model: {model}\n")

    try:
        import json
        from pathlib import Path
        from datetime import datetime
        from deepr.services.team_architect import TeamArchitect, TeamSynthesizer
        from deepr.services.research_planner import ResearchPlanner
        from deepr.services.batch_executor import BatchExecutor
        from deepr.storage.local import LocalStorage

        # Phase 1: GPT-5 designs optimal team for THIS question
        if company:
            click.echo(f"[Phase 0] Researching {company}'s leadership for grounded personas...\n")

        click.echo("[Phase 1] GPT-5 assembling dream team for this question...\n")

        architect = TeamArchitect(model="gpt-5")
        team = architect.design_team(
            question=question,
            context=context,
            team_size=team_size,
            research_company=company
        )

        click.echo(f"Assembled {len(team)}-person dream team:\n")
        for i, member in enumerate(team, 1):
            click.echo(f"{i}. {member['role']}")
            click.echo(f"   Focus: {member['focus']}")
            click.echo(f"   Perspective: {member['perspective']}")
            click.echo(f"   Why: {member['rationale']}\n")

        if not yes:
            click.confirm("\nProceed with research?", abort=True)

        # Phase 2: Create research tasks for each team member
        click.echo("\n[Phase 2] Creating research tasks for each team member...\n")

        planner = ResearchPlanner(model="gpt-5")
        tasks = []

        for i, member in enumerate(team, 1):
            # Build role-specific research prompt
            role_prompt = f"""You are: {member['role']}
Your perspective: {member['perspective']}
Your focus: {member['focus']}

Question: {question}

{f'Context: {context}' if context else ''}

Research this question from YOUR perspective as a {member['role']}.
Focus specifically on: {member['focus']}

Provide analysis and insights from your unique perspective. Don't try to cover everything - stay in your lane as {member['role']}."""

            task = {
                "id": i,
                "title": f"{member['role']}: {member['focus'][:50]}...",
                "prompt": role_prompt,
                "type": "analysis",
                "team_member": member,
                "model": model
            }
            tasks.append(task)

            click.echo(f"  Task {i}: {member['role']}")

        # Save plan
        plan_path = Path(".deepr") / "team_research_plan.json"
        plan_path.parent.mkdir(exist_ok=True)

        plan_data = {
            "question": question,
            "context": context,
            "team": team,
            "tasks": tasks,
            "created_at": datetime.utcnow().isoformat(),
            "status": "ready"
        }

        with open(plan_path, 'w') as f:
            json.dump(plan_data, f, indent=2)

        click.echo(f"\n[OK] Team research plan saved to {plan_path}")

        # Phase 3: Execute research with role context
        click.echo("\n[Phase 3] Team members conducting research...\n")
        click.echo(f"Each member will research independently from their perspective.")
        click.echo(f"This will take ~{len(tasks) * 5}-{len(tasks) * 15} minutes.\n")

        # Execute asynchronously
        executor = BatchExecutor()
        storage = LocalStorage()

        async def run_research():
            results = await executor.execute_batch(
                tasks=tasks,
                campaign_id=f"team-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                storage=storage
            )
            return results

        results = asyncio.run(run_research())

        # Update plan with results
        plan_data["results"] = results
        plan_data["status"] = "researched"
        with open(plan_path, 'w') as f:
            json.dump(plan_data, f, indent=2)

        click.echo(f"\n[OK] Research complete! {len(results)} team members finished.\n")

        # Phase 4: Synthesize with attribution
        click.echo("[Phase 4] Lead Researcher synthesizing team perspectives...\n")

        synthesizer = TeamSynthesizer(model="gpt-5")
        report = synthesizer.synthesize_with_conflict_analysis(
            question=question,
            team_results=results
        )

        # Save report
        report_path = Path(".deepr") / "team_research_report.md"
        with open(report_path, 'w') as f:
            f.write(report)

        click.echo(report)
        click.echo(f"\n\n[OK] Full report saved to {report_path}")

        # Show cost
        total_cost = sum(r.get("cost", 0) for r in results)
        click.echo(f"\nTotal cost: ${total_cost:.2f}")

    except Exception as e:
        click.echo(f"\n[ERROR] {e}", err=True)
        import traceback
        traceback.print_exc()
        raise click.Abort()


@team.command()
def status():
    """Show status of current team research."""
    from pathlib import Path
    import json

    plan_path = Path(".deepr") / "team_research_plan.json"

    if not plan_path.exists():
        click.echo("No team research in progress")
        return

    with open(plan_path) as f:
        plan = json.load(f)

    click.echo(f"\nQuestion: {plan['question']}")
    click.echo(f"Status: {plan['status']}")
    click.echo(f"Team size: {len(plan['team'])}")

    if plan['status'] == 'researched':
        results = plan.get('results', [])
        completed = sum(1 for r in results if r.get('status') == 'completed')
        click.echo(f"Progress: {completed}/{len(results)} completed")
