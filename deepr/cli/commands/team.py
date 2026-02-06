"""Team commands - dynamic dream team research."""

import asyncio
from typing import Optional

import click

from deepr.cli.colors import console, print_section_header, print_success


async def run_dream_team(
    question: str, model: str = "o4-mini-deep-research", perspectives: int = 6, provider: str = None
):
    """
    Execute dream team research (async wrapper for new CLI).

    This is called by the new 'deepr run team' command.

    Args:
        question: The question to research
        model: Model to use for research
        perspectives: Number of team perspectives
        provider: Provider to use (defaults to model-based routing)
    """
    import os
    import uuid
    from datetime import datetime, timezone

    from deepr.config import load_config
    from deepr.providers import create_provider
    from deepr.providers.base import ResearchRequest, ToolConfig
    from deepr.queue import create_queue
    from deepr.queue.base import JobStatus, ResearchJob
    from deepr.services.team_architect import TeamArchitect
    from deepr.storage import create_storage

    # Load config
    config = load_config()

    # Determine provider based on model if not specified
    if provider is None:
        is_deep_research = "deep-research" in model.lower()
        if is_deep_research:
            provider = os.getenv("DEEPR_DEEP_RESEARCH_PROVIDER", "openai")
        else:
            provider = os.getenv("DEEPR_DEFAULT_PROVIDER", "xai")
        click.echo(f"[Using {provider} provider for team research]")

    # Get provider-specific API key
    if provider == "gemini":
        api_key = config.get("gemini_api_key")
    elif provider in ["grok", "xai"]:
        api_key = config.get("xai_api_key")
        provider = "xai"  # Normalize
    elif provider == "azure":
        api_key = config.get("azure_api_key")
    else:  # openai
        api_key = config.get("api_key")
        provider = "openai"

    # Phase 1: Design team
    architect = TeamArchitect(model="gpt-5")
    team = architect.design_team(
        question=question,
        context=None,
        team_size=perspectives,
        research_company=None,
        perspective_lens=None,
        adversarial=False,
    )

    click.echo(f"\nTeam assembled with {len(team)} perspectives:")
    for i, member in enumerate(team, 1):
        # Handle Unicode encoding issues on Windows
        role = member["role"].encode("ascii", "replace").decode("ascii")
        focus = member["focus"][:60].encode("ascii", "replace").decode("ascii")
        click.echo(f"  {i}. {role}: {focus}...")

    # Phase 2: Execute research for each perspective
    provider_instance = create_provider(provider, api_key=api_key)
    queue = create_queue("local")
    storage = create_storage(config.get("storage", "local"), base_path=config.get("results_dir", "data/reports"))

    click.echo(f"\nExecuting research from {len(team)} perspectives...")
    results = []

    for i, member in enumerate(team, 1):
        # Create research prompt for this perspective
        prompt = f"""Question: {question}

Perspective: {member["role"]}
Focus: {member["focus"]}
Rationale: {member["rationale"]}

Provide your analysis from this perspective."""

        job_id = f"team-{uuid.uuid4().hex[:12]}"

        # Store job in queue first
        job = ResearchJob(
            id=job_id,
            prompt=prompt,
            model=model,
            provider=provider,
            status=JobStatus.PROCESSING,
            submitted_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc),
            enable_web_search=True,
            metadata={"team_role": member["role"], "question": question},
        )
        await queue.enqueue(job)

        # Handle Unicode encoding issues on Windows
        role = member["role"].encode("ascii", "replace").decode("ascii")
        click.echo(f"\n[{i}/{len(team)}] {role}...")

        # Submit to provider
        try:
            request = ResearchRequest(
                prompt=prompt,
                model=model,
                system_message=f"You are a research expert analyzing from the perspective of: {member['role']}. Focus on: {member['focus']}",
                tools=[ToolConfig(type="web_search")] if provider != "xai" else [],  # xAI auto-enables web search
            )

            provider_job_id = await provider_instance.submit_research(request)

            # Update job with provider job ID
            await queue.update_status(job_id, JobStatus.PROCESSING, provider_job_id=provider_job_id)

            # Wait for completion (immediate for xAI/Gemini, polling for OpenAI)
            response = await provider_instance.get_status(provider_job_id)

            # For async providers, poll until complete
            import asyncio

            max_wait = 600  # 10 minutes max
            waited = 0
            while response.status in ["queued", "in_progress"] and waited < max_wait:
                await asyncio.sleep(5)
                waited += 5
                response = await provider_instance.get_status(provider_job_id)

            if response.status == "completed":
                # Extract content
                content = ""
                if response.output:
                    for block in response.output:
                        if block.get("type") == "message":
                            for item in block.get("content", []):
                                if item.get("type") in ["output_text", "text"]:
                                    text = item.get("text", "")
                                    if text:
                                        content += text + "\n"

                # Save report
                report_metadata = await storage.save_report(
                    job_id=job_id,
                    filename="report.md",
                    content=content.encode("utf-8"),
                    content_type="text/markdown",
                    metadata={
                        "prompt": prompt,
                        "model": model,
                        "team_role": member["role"],
                        "question": question,
                    },
                )

                # Update queue
                await queue.update_status(job_id, JobStatus.COMPLETED)
                cost = response.usage.cost if response.usage else 0.0
                await queue.update_results(job_id, report_paths={"markdown": report_metadata.url}, cost=cost)

                results.append({"job_id": job_id, "role": member["role"], "content": content, "cost": cost})

                console.print(f"  [success]Completed[/success] [dim](${cost:.4f})[/dim]")

            else:
                error_msg = response.error if response.error else "Unknown error"
                await queue.update_status(job_id, JobStatus.FAILED, error=error_msg)
                console.print(f"  [error]Failed: {error_msg}[/error]")

        except Exception as e:
            await queue.update_status(job_id, JobStatus.FAILED, error=str(e))
            console.print(f"  [error]Error: {e}[/error]")

    total_cost = sum(r.get("cost", 0) for r in results)
    print_success("Team research completed!")
    click.echo(f"  Perspectives analyzed: {len(results)}/{len(team)}")
    click.echo(f"  Total cost: ${total_cost:.4f}")

    return results


@click.group()
def team():
    """Assemble dynamic research teams with diverse perspectives."""
    pass


@team.command()
@click.argument("question")
@click.option("--team-size", "-n", default=5, type=click.IntRange(3, 8), help="Number of team members (3-8)")
@click.option("--context", "-c", default=None, help="Additional context for research")
@click.option(
    "--company", default=None, help="Company name to research for grounded personas (e.g., 'Anthropic', 'OpenAI')"
)
@click.option(
    "--perspective",
    "-p",
    default=None,
    help="Cultural/demographic perspective lens (e.g., 'Japanese business culture', 'Jewish perspective', 'Gen Z', 'Rural American')",
)
@click.option("--adversarial", is_flag=True, help="Weight team toward skeptical/devil's advocate perspectives")
@click.option(
    "--model",
    "-m",
    default="o4-mini-deep-research",
    type=click.Choice(["o4-mini-deep-research", "o3-deep-research"]),
    help="Deep research model for execution",
)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation and execute immediately")
def analyze(
    question: str,
    team_size: int,
    context: Optional[str],
    company: Optional[str],
    perspective: Optional[str],
    adversarial: bool,
    model: str,
    yes: bool,
):
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
        deepr team analyze "Our Q2 launch plan" --adversarial  # Devil's advocate mode
        deepr team analyze "How should we enter the Japanese market?" --perspective "Japanese business culture"
        deepr team analyze "Community engagement strategy" --perspective "Gen Z social media users"
    """
    print_section_header("Dynamic Dream Team Research")

    click.echo(f"\nQuestion: {question}")
    if context:
        click.echo(f"Context: {context[:100]}..." if len(context) > 100 else f"Context: {context}")
    if company:
        click.echo(f"Company: {company} (will research leadership for grounded personas)")
    if perspective:
        click.echo(f"Perspective lens: {perspective}")
    if adversarial:
        click.echo("Mode: Adversarial (weighted toward skeptical/devil's advocate perspectives)")
    click.echo(f"Team size: {team_size} members")
    click.echo(f"Model: {model}\n")

    try:
        import json
        from datetime import datetime, timezone
        from pathlib import Path

        from deepr.services.batch_executor import BatchExecutor
        from deepr.services.team_architect import TeamArchitect, TeamSynthesizer
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
            research_company=company,
            perspective_lens=perspective,
            adversarial=adversarial,
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

        tasks = []

        for i, member in enumerate(team, 1):
            # Build role-specific research prompt
            role_prompt = f"""You are: {member["role"]}
Your perspective: {member["perspective"]}
Your focus: {member["focus"]}

Question: {question}

{f"Context: {context}" if context else ""}

Research this question from YOUR perspective as a {member["role"]}.
Focus specifically on: {member["focus"]}

Provide analysis and insights from your unique perspective. Don't try to cover everything - stay in your lane as {member["role"]}."""

            task = {
                "id": i,
                "title": f"{member['role']}: {member['focus'][:50]}...",
                "prompt": role_prompt,
                "type": "analysis",
                "team_member": member,
                "model": model,
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
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "ready",
        }

        with open(plan_path, "w") as f:
            json.dump(plan_data, f, indent=2)

        print_success(f"Team research plan saved to {plan_path}")

        # Phase 3: Execute research with role context
        click.echo("\n[Phase 3] Team members conducting research...\n")
        click.echo("Each member will research independently from their perspective.")
        click.echo(f"This will take ~{len(tasks) * 5}-{len(tasks) * 15} minutes.\n")

        # Execute asynchronously
        executor = BatchExecutor()
        storage = LocalStorage()

        async def run_research():
            results = await executor.execute_batch(
                tasks=tasks, campaign_id=f"team-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}", storage=storage
            )
            return results

        results = asyncio.run(run_research())

        # Update plan with results
        plan_data["results"] = results
        plan_data["status"] = "researched"
        with open(plan_path, "w") as f:
            json.dump(plan_data, f, indent=2)

        print_success(f"Research complete! {len(results)} team members finished.")

        # Phase 4: Synthesize with attribution
        click.echo("\n[Phase 4] Lead Researcher synthesizing team perspectives...\n")

        synthesizer = TeamSynthesizer(model="gpt-5")
        report = synthesizer.synthesize_with_conflict_analysis(question=question, team_results=results)

        # Save report
        report_path = Path(".deepr") / "team_research_report.md"
        with open(report_path, "w") as f:
            f.write(report)

        click.echo(report)
        print_success(f"Full report saved to {report_path}")

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
    import json
    from pathlib import Path

    plan_path = Path(".deepr") / "team_research_plan.json"

    if not plan_path.exists():
        click.echo("No team research in progress")
        return

    with open(plan_path) as f:
        plan = json.load(f)

    click.echo(f"\nQuestion: {plan['question']}")
    click.echo(f"Status: {plan['status']}")
    click.echo(f"Team size: {len(plan['team'])}")

    if plan["status"] == "researched":
        results = plan.get("results", [])
        completed = sum(1 for r in results if r.get("status") == "completed")
        click.echo(f"Progress: {completed}/{len(results)} completed")
