"""Run research jobs with modern CLI interface."""

import click
import asyncio
from pathlib import Path
from typing import Optional, List
from deepr.queue.local_queue import SQLiteQueue
from deepr.queue.base import ResearchJob, JobStatus
from deepr.cli.commands.budget import check_budget_approval
from datetime import datetime
import json
import uuid


def estimate_cost(model: str, enable_web_search: bool = True) -> float:
    """Simple cost estimation."""
    # Based on real API tests
    if "o4-mini" in model:
        return 0.10  # $0.10 average for o4-mini
    elif "o3" in model:
        return 0.50  # $0.50 average for o3
    else:
        return 0.15  # Default estimate


@click.group()
def run():
    """Run research jobs (single, campaign, or team)."""
    pass


@run.command()
@click.argument("query")
@click.option("--model", "-m", default="o4-mini-deep-research", help="Research model to use")
@click.option("--provider", "-p", default="openai", type=click.Choice(["openai", "azure", "gemini", "grok"]), help="Research provider (openai, azure, gemini, grok)")
@click.option("--no-web", is_flag=True, help="Disable web search")
@click.option("--no-code", is_flag=True, help="Disable code interpreter")
@click.option("--upload", "-u", multiple=True, help="Upload files for context")
@click.option("--limit", "-l", type=float, help="Cost limit in dollars")
@click.option("--yes", "-y", is_flag=True, help="Skip budget confirmation")
def focus(
    query: str,
    model: str,
    provider: str,
    no_web: bool,
    no_code: bool,
    upload: tuple,
    limit: Optional[float],
    yes: bool,
):
    """Run a focused research job (quick, single-turn research).

    Examples:
        deepr run focus "Analyze AI code editor market 2025"
        deepr run focus "Latest quantum computing trends" -m o3-deep-research
        deepr run focus "Company analysis" --upload data.csv --limit 5.00
        deepr run focus "Query" --provider gemini -m gemini-2.5-flash
        deepr run focus "Latest from xAI" --provider grok -m grok-4-fast
    """
    asyncio.run(_run_single(query, model, provider, no_web, no_code, upload, limit, yes))


@run.command()
@click.argument("query")
@click.option("--model", "-m", default="o4-mini-deep-research", help="Research model to use")
@click.option("--provider", "-p", default="openai", type=click.Choice(["openai", "azure", "gemini", "grok"]), help="Research provider (openai, azure, gemini, grok)")
@click.option("--no-web", is_flag=True, help="Disable web search")
@click.option("--no-code", is_flag=True, help="Disable code interpreter")
@click.option("--upload", "-u", multiple=True, help="Upload files for context")
@click.option("--limit", "-l", type=float, help="Cost limit in dollars")
@click.option("--yes", "-y", is_flag=True, help="Skip budget confirmation")
def single(
    query: str,
    model: str,
    provider: str,
    no_web: bool,
    no_code: bool,
    upload: tuple,
    limit: Optional[float],
    yes: bool,
):
    """[DEPRECATED: Use 'deepr run focus'] Run a single research job.

    Examples:
        deepr run single "Analyze AI code editor market 2025"
        deepr run single "Latest quantum computing trends" -m o3-deep-research
        deepr run single "Company analysis" --upload data.csv --limit 5.00
        deepr run single "Query" --provider gemini -m gemini-2.5-flash
        deepr run single "Latest from xAI" --provider grok -m grok-4-fast
    """
    click.echo("⚠️  DEPRECATION WARNING: 'deepr run single' is deprecated. Use 'deepr run focus' instead.\n")
    asyncio.run(_run_single(query, model, provider, no_web, no_code, upload, limit, yes))


async def _run_single(
    query: str,
    model: str,
    provider: str,
    no_web: bool,
    no_code: bool,
    upload: tuple,
    limit: Optional[float],
    yes: bool,
):
    """Execute single research job."""
    click.echo("\n" + "="*70)
    click.echo("  DEEPR - Single Research")
    click.echo("="*70 + "\n")

    # Estimate cost
    estimated_cost = estimate_cost(model, enable_web_search=not no_web)

    click.echo(f"Query: {query}")
    click.echo(f"Provider: {provider}")
    click.echo(f"Model: {model}")
    click.echo(f"Estimated cost: ${estimated_cost:.2f}")

    if upload:
        click.echo(f"Files: {', '.join(upload)}")

    click.echo()

    # Budget check
    if not yes and not check_budget_approval(estimated_cost):
        if not click.confirm(f"Proceed with estimated cost ${estimated_cost:.2f}?"):
            click.echo("Cancelled.")
            return

    # Handle file uploads
    document_ids = []
    if upload:
        click.echo("Uploading files...")
        # TODO: Implement file upload
        click.echo("  (File upload not yet implemented)")

    # Submit job to queue
    click.echo("Submitting research job...")

    job = ResearchJob(
        id=f"research-{uuid.uuid4().hex[:12]}",
        prompt=query,
        model=model,
        provider=provider,
        status=JobStatus.QUEUED,
        submitted_at=datetime.utcnow(),
        enable_web_search=not no_web,
        enable_code_interpreter=not no_code,
        documents=document_ids,
        cost_limit=limit,
    )

    queue = SQLiteQueue()
    job_id = await queue.enqueue(job)

    # Submit to provider API
    try:
        from deepr.providers import create_provider
        from deepr.providers.base import ResearchRequest, ToolConfig
        from deepr.config import load_config

        config = load_config()

        # Get provider-specific API key
        if provider == "gemini":
            api_key = config.get("gemini_api_key")
        elif provider == "grok":
            api_key = config.get("xai_api_key")
        elif provider == "azure":
            api_key = config.get("azure_api_key")
        else:  # openai
            api_key = config.get("api_key")

        provider_instance = create_provider(provider, api_key=api_key)

        # Build tools list (provider-specific tool names)
        tools = []
        if not no_web:
            # Grok/xAI uses "web_search", others use "web_search_preview"
            tool_name = "web_search" if provider == "grok" else "web_search_preview"
            tools.append(ToolConfig(type=tool_name))
        if not no_code:
            tools.append(ToolConfig(type="code_interpreter"))

        # Create research request
        # Note: Grok/xAI doesn't support background parameter
        request = ResearchRequest(
            prompt=query,
            model=model,
            system_message="You are a research assistant. Provide comprehensive, citation-backed analysis.",
            tools=tools,
            background=True if provider in ["openai", "azure"] else False,
            document_ids=document_ids if document_ids else None,
        )

        # Submit to provider
        provider_job_id = await provider_instance.submit_research(request)

        # For Gemini and Grok, research completes immediately - check and save results
        if provider in ["gemini", "grok"]:
            response = await provider_instance.get_status(provider_job_id)

            if response.status == "completed":
                # Extract content
                content = ""
                if response.output:
                    for block in response.output:
                        if block.get('type') == 'message':
                            for item in block.get('content', []):
                                if item.get('type') in ['output_text', 'text']:
                                    text = item.get('text', '')
                                    if text:
                                        content += text + "\n"

                # Save to storage
                from deepr.storage import create_storage
                storage = create_storage(
                    config.get("storage", "local"),
                    base_path=config.get("results_dir", "data/reports")
                )

                report_metadata = await storage.save_report(
                    job_id=job_id,
                    filename="report.md",
                    content=content.encode('utf-8'),
                    content_type="text/markdown",
                    metadata={
                        "prompt": query,
                        "model": model,
                        "status": "completed",
                        "provider_job_id": provider_job_id,
                    }
                )

                # Update queue as completed
                await queue.update_status(job_id, JobStatus.COMPLETED)
                if response.usage and response.usage.cost:
                    await queue.update_results(
                        job_id,
                        report_paths={"markdown": report_metadata.url},
                        cost=response.usage.cost,
                        tokens_used=response.usage.total_tokens
                    )

                click.echo(f"\nJob completed: {job_id[:12]}")
                click.echo(f"Cost: ${response.usage.cost:.4f}")
                click.echo(f"Report: {report_metadata.url}")
            else:
                # Update as processing if not yet complete
                await queue.update_status(
                    job_id=job_id,
                    status=JobStatus.PROCESSING,
                    provider_job_id=provider_job_id
                )
                click.echo(f"\nJob submitted: {job_id[:12]}")
                click.echo(f"Provider job ID: {provider_job_id}")
        else:
            # For OpenAI/Azure, update as processing
            await queue.update_status(
                job_id=job_id,
                status=JobStatus.PROCESSING,
                provider_job_id=provider_job_id
            )

            click.echo(f"\nJob submitted: {job_id[:12]}")
            click.echo(f"Provider job ID: {provider_job_id}")

    except Exception as e:
        click.echo(f"\nWarning: Failed to submit to provider: {e}")
        click.echo(f"Job queued locally: {job_id[:12]}")
        click.echo(f"You can try retrieving results later with: deepr get {job_id[:12]}")

    click.echo(f"\nCheck status: deepr status {job_id[:12]}")
    click.echo(f"View results: deepr get {job_id[:12]}")
    click.echo(f"List all jobs: deepr list")


@run.command()
@click.argument("scenario")
@click.option("--model", "-m", default="o4-mini-deep-research", help="Research model")
@click.option("--lead", default="gpt-5", help="Lead planner model")
@click.option("--phases", "-p", type=int, default=3, help="Number of phases")
@click.option("--yes", "-y", is_flag=True, help="Skip budget confirmation")
def project(
    scenario: str,
    model: str,
    lead: str,
    phases: int,
    yes: bool,
):
    """Run a multi-phase research project with context chaining.

    The lead model plans the research, then executes multiple phases
    with context chaining between them.

    Examples:
        deepr run project "Ford EV strategy for 2026"
        deepr run project "Market entry analysis" --phases 4
        deepr run project "Competitive landscape" -m o3-deep-research
    """
    asyncio.run(_run_campaign(scenario, model, lead, phases, yes))


@run.command()
@click.argument("scenario")
@click.option("--model", "-m", default="o4-mini-deep-research", help="Research model")
@click.option("--lead", default="gpt-5", help="Lead planner model")
@click.option("--phases", "-p", type=int, default=3, help="Number of phases")
@click.option("--yes", "-y", is_flag=True, help="Skip budget confirmation")
def campaign(
    scenario: str,
    model: str,
    lead: str,
    phases: int,
    yes: bool,
):
    """[DEPRECATED: Use 'deepr run project'] Run a multi-phase research campaign.

    The lead model plans the research, then executes multiple phases
    with context chaining between them.

    Examples:
        deepr run campaign "Ford EV strategy for 2026"
        deepr run campaign "Market entry analysis" --phases 4
        deepr run campaign "Competitive landscape" -m o3-deep-research
    """
    click.echo("⚠️  DEPRECATION WARNING: 'deepr run campaign' is deprecated. Use 'deepr run project' instead.\n")
    asyncio.run(_run_campaign(scenario, model, lead, phases, yes))


async def _run_campaign(
    scenario: str,
    model: str,
    lead: str,
    phases: int,
    yes: bool,
):
    """Execute campaign."""
    click.echo("\n" + "="*70)
    click.echo("  DEEPR - Multi-Phase Campaign")
    click.echo("="*70 + "\n")

    # Estimate cost (phases * per-job cost)
    per_job_cost = estimate_cost(model, enable_web_search=True)
    estimated_cost = per_job_cost * phases

    click.echo(f"Scenario: {scenario}")
    click.echo(f"Lead model: {lead}")
    click.echo(f"Research model: {model}")
    click.echo(f"Phases: {phases}")
    click.echo(f"Estimated cost: ${estimated_cost:.2f} ({phases} x ${per_job_cost:.2f})")
    click.echo()

    # Budget check
    if not yes and not check_budget_approval(estimated_cost):
        if not click.confirm(f"Proceed with estimated cost ${estimated_cost:.2f}?"):
            click.echo("Cancelled.")
            return

    click.echo("Planning campaign phases...")

    # Import prep functionality
    from deepr.cli.commands.prep import execute_plan
    from deepr.planner.planner import plan_research_campaign

    # Generate plan using lead model
    plan = await plan_research_campaign(scenario, lead, phases)

    click.echo(f"\nCampaign plan generated:")
    click.echo(f"  Tasks: {len(plan['tasks'])}")
    click.echo()

    # Execute campaign
    click.echo("Executing campaign phases...")
    await execute_plan(plan, model)

    click.echo(f"\nCampaign launched!")
    click.echo(f"Check progress: deepr list")


@run.command()
@click.argument("question")
@click.option("--model", "-m", default="o4-mini-deep-research", help="Research model")
@click.option("--perspectives", "-p", type=int, default=6, help="Number of perspectives")
@click.option("--yes", "-y", is_flag=True, help="Skip budget confirmation")
def team(
    question: str,
    model: str,
    perspectives: int,
    yes: bool,
):
    """Run research with multiple perspectives (dream team).

    Uses Six Thinking Hats methodology to analyze the question
    from different angles simultaneously.

    Examples:
        deepr run team "Should we pivot to enterprise?"
        deepr run team "Evaluate merger opportunity" --perspectives 8
        deepr run team "Technology decision" -m o3-deep-research
    """
    asyncio.run(_run_team(question, model, perspectives, yes))


async def _run_team(
    question: str,
    model: str,
    perspectives: int,
    yes: bool,
):
    """Execute team research."""
    click.echo("\n" + "="*70)
    click.echo("  DEEPR - Dream Team Research")
    click.echo("="*70 + "\n")

    # Estimate cost
    per_job_cost = estimate_cost(model, enable_web_search=True)
    estimated_cost = per_job_cost * perspectives

    click.echo(f"Question: {question}")
    click.echo(f"Model: {model}")
    click.echo(f"Perspectives: {perspectives}")
    click.echo(f"Estimated cost: ${estimated_cost:.2f} ({perspectives} x ${per_job_cost:.2f})")
    click.echo()

    # Budget check
    if not yes and not check_budget_approval(estimated_cost):
        if not click.confirm(f"Proceed with estimated cost ${estimated_cost:.2f}?"):
            click.echo("Cancelled.")
            return

    click.echo("Assembling research team...")

    # Import team functionality
    from deepr.cli.commands.team import run_dream_team

    # Execute team research
    await run_dream_team(question, model, perspectives)

    click.echo(f"\nTeam research launched!")
    click.echo(f"Check progress: deepr list")


@run.command()
@click.argument("topic")
@click.option("--model", "-m", default="o4-mini-deep-research", help="Research model to use")
@click.option("--provider", "-p", default="openai", type=click.Choice(["openai", "azure", "gemini", "grok"]), help="Research provider")
@click.option("--upload", "-u", multiple=True, help="Upload existing documentation for context")
@click.option("--limit", "-l", type=float, help="Cost limit in dollars")
@click.option("--yes", "-y", is_flag=True, help="Skip budget confirmation")
def docs(
    topic: str,
    model: str,
    provider: str,
    upload: tuple,
    limit: Optional[float],
    yes: bool,
):
    """Run documentation-oriented research.

    Focused on creating comprehensive, well-structured documentation
    with clear explanations, examples, and references.

    Examples:
        deepr run docs "API authentication flow"
        deepr run docs "Database schema design" --upload existing_docs.md
        deepr run docs "Deployment guide for Kubernetes"
    """
    # Use the single research flow with documentation-optimized system message
    system_message = """You are a technical documentation expert. Your goal is to create comprehensive,
well-structured documentation that is clear, accurate, and useful. Include:
- Clear explanations of concepts
- Practical examples and code samples
- Common pitfalls and troubleshooting tips
- References and additional resources
- Well-organized structure with headings and sections"""

    # Call _run_single with docs-specific parameters
    asyncio.run(_run_single(
        query=f"Create comprehensive documentation for: {topic}",
        model=model,
        provider=provider,
        no_web=False,  # Enable web search for docs research
        no_code=False,  # Enable code interpreter for examples
        upload=upload,
        limit=limit,
        yes=yes
    ))


# Aliases
@click.command(name="r")
@click.argument("query")
@click.option("--model", "-m", default="o4-mini-deep-research")
@click.option("--no-web", is_flag=True)
@click.option("--no-code", is_flag=True)
@click.option("--upload", "-u", multiple=True)
@click.option("--limit", "-l", type=float)
@click.option("--yes", "-y", is_flag=True)
def run_alias(query, model, no_web, no_code, upload, limit, yes):
    """Quick alias for 'deepr run' - run a single research job."""
    asyncio.run(_run_single(query, model, no_web, no_code, upload, limit, yes))


if __name__ == "__main__":
    run()
