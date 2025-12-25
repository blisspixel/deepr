"""Run research jobs with modern CLI interface."""

import click
import asyncio
import os
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
    click.echo("[DEPRECATION] 'deepr run single' is deprecated. Use 'deepr run focus' instead.\n")
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
    vector_store_id = None
    if upload:
        click.echo("Uploading files...")
        try:
            from deepr.providers import create_provider
            from deepr.config import load_config
            from deepr.utils.paths import resolve_file_path, resolve_glob_pattern, normalize_path_for_display

            config = load_config()

            # Get provider-specific API key
            if provider == "gemini":
                api_key = config.get("gemini_api_key")
            elif provider in ["grok", "xai"]:
                api_key = config.get("xai_api_key")
            elif provider == "azure":
                api_key = config.get("azure_api_key")
            else:  # openai
                api_key = config.get("api_key")

            provider_instance = create_provider(provider, api_key=api_key)

            # Resolve all file paths (handles globs, Windows paths, spaces, etc.)
            resolved_files = []
            for file_pattern in upload:
                try:
                    # Check if it's a glob pattern
                    if '*' in file_pattern or '?' in file_pattern:
                        matched = resolve_glob_pattern(file_pattern, must_match=True)
                        resolved_files.extend(matched)
                        click.echo(f"  Pattern '{file_pattern}' matched {len(matched)} file(s)")
                    else:
                        # Single file
                        resolved = resolve_file_path(file_pattern, must_exist=True)
                        resolved_files.append(resolved)
                except FileNotFoundError as e:
                    click.echo(f"  [X] {e}")
                    continue

            if not resolved_files:
                click.echo("  [!] No files to upload")
            else:
                click.echo(f"  Found {len(resolved_files)} file(s) to upload\n")

            # Upload each file
            uploaded_files = []
            for file_path in resolved_files:
                display_name = file_path.name
                display_path = normalize_path_for_display(file_path)

                click.echo(f"  Uploading: {display_name}")
                click.echo(f"    Path: {display_path}")
                try:
                    file_id = await provider_instance.upload_document(str(file_path))
                    uploaded_files.append(file_id)
                    click.echo(f"    [OK] Uploaded")
                except Exception as e:
                    click.echo(f"    [X] Failed: {e}")
                click.echo()

            if not uploaded_files:
                click.echo("  [!] No files uploaded successfully")
            else:
                # For OpenAI, create vector store
                if provider in ["openai", "azure"]:
                    click.echo("  Creating vector store...")
                    try:
                        from deepr.providers.base import VectorStore
                        vs = await provider_instance.create_vector_store(
                            name=f"research-{uuid.uuid4().hex[:8]}",
                            file_ids=uploaded_files
                        )
                        vector_store_id = vs.id
                        click.echo(f"  [OK] Vector store created: {vs.id[:20]}...")

                        # Wait for ingestion with progress feedback
                        click.echo("  Waiting for file processing...")
                        click.echo("  (This may take 15-60 seconds depending on file size)")
                        ready = await provider_instance.wait_for_vector_store(
                            vs.id,
                            timeout=300,
                            poll_interval=2.0
                        )
                        if ready:
                            click.echo("  [OK] Files ready for research")
                        else:
                            click.echo("  [!] Files still processing (continuing anyway)")
                            click.echo("  Note: Research may proceed with partial file indexing")
                    except Exception as e:
                        click.echo(f"  [X] Vector store creation failed: {e}")
                        vector_store_id = None

                # For Gemini, files are referenced directly
                elif provider == "gemini":
                    document_ids = uploaded_files
                    click.echo(f"  [OK] {len(uploaded_files)} files ready for research")

                # For Grok/xAI, document collections not yet implemented
                elif provider in ["grok", "xai"]:
                    click.echo("  [!] xAI file upload not yet fully supported")
                    click.echo("  Files uploaded but may not be used in research")
                    document_ids = uploaded_files

        except Exception as e:
            click.echo(f"  [X] File upload failed: {e}")
            click.echo("  Continuing without files...")

    # Submit job to queue
    click.echo("Submitting research job...")

    # Prepare job metadata for cleanup tracking
    job_metadata = {}
    if vector_store_id:
        job_metadata["vector_store_id"] = vector_store_id
        job_metadata["cleanup_vector_store"] = True  # Auto-cleanup after job completes
    if upload:
        job_metadata["uploaded_files"] = list(upload)

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
        metadata=job_metadata,
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
        elif provider in ["grok", "xai"]:
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
            tool_name = "web_search" if provider in ["grok", "xai"] else "web_search_preview"
            tools.append(ToolConfig(type=tool_name))
        if not no_code:
            tools.append(ToolConfig(type="code_interpreter"))

        # Add file_search tool for OpenAI/Azure when vector store is available
        if vector_store_id and provider in ["openai", "azure"]:
            tools.append(ToolConfig(
                type="file_search",
                vector_store_ids=[vector_store_id]
            ))

        # Validate tools for deep research models
        if provider in ["openai", "azure"] and "deep-research" in model and not tools:
            click.echo(f"\n[X] Error: {model} requires at least one tool (web search, code interpreter, or file upload)")
            click.echo("    Remove --no-web and/or --no-code flags, or add --upload for file search")
            return

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

        # For Gemini and Grok/xAI, research completes immediately - check and save results
        if provider in ["gemini", "grok", "xai"]:
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
    click.echo("[DEPRECATION] 'deepr run campaign' is deprecated. Use 'deepr run project' instead.\n")
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
    click.echo("\nNOTE: This command is deprecated. Please use 'deepr prep plan' and 'deepr prep execute' for better control.\n")

    # Import prep functionality - use the working implementation
    from deepr.services.research_planner import ResearchPlanner
    from deepr.cli.commands.prep import _execute_plan_sync

    # Generate plan using lead model (planner for planning, model for execution)
    planner_svc = ResearchPlanner(model=lead)
    tasks = planner_svc.plan_research(
        scenario=scenario,
        max_tasks=phases,
        context=None
    )

    # Add task IDs and model info
    for i, task in enumerate(tasks, 1):
        task['id'] = i
        task['model'] = model
        task['approved'] = True  # Auto-approve for deprecated command

    plan = {
        "scenario": scenario,
        "tasks": tasks,
        "model": model,
        "metadata": {"planner": lead}
    }

    click.echo(f"\nCampaign plan generated:")
    click.echo(f"  Tasks: {len(plan['tasks'])}")
    click.echo()

    # Execute campaign
    click.echo("Executing campaign phases...")

    # Import the async executor instead of the sync wrapper
    from deepr.services.batch_executor import BatchExecutor
    from deepr.storage import create_storage
    from deepr.queue import create_queue
    from deepr.config import load_config
    from deepr.providers import create_provider
    from deepr.services.context_builder import ContextBuilder
    import time
    import os

    config = load_config()

    # Determine provider based on model
    is_deep_research = "deep-research" in model.lower()
    if is_deep_research:
        provider_name = os.getenv("DEEPR_DEEP_RESEARCH_PROVIDER", "openai")
    else:
        provider_name = os.getenv("DEEPR_DEFAULT_PROVIDER", "xai")

    # Get API key
    if provider_name == "gemini":
        api_key = config.get("gemini_api_key")
    elif provider_name in ["grok", "xai"]:
        api_key = config.get("xai_api_key")
        provider_name = "xai"
    elif provider_name == "azure":
        api_key = config.get("azure_api_key")
    else:
        api_key = config.get("api_key")
        provider_name = "openai"

    # Initialize services
    queue = create_queue("local")
    provider_instance = create_provider(provider_name, api_key=api_key)
    storage = create_storage(
        config.get("storage", "local"),
        base_path=config.get("results_dir", "data/reports")
    )
    context_builder = ContextBuilder(api_key=config.get("api_key"))

    executor = BatchExecutor(
        queue=queue,
        provider=provider_instance,
        storage=storage,
        context_builder=context_builder
    )

    campaign_id = f"campaign-{int(time.time())}"
    results = await executor.execute_campaign(tasks, campaign_id)

    click.echo(f"\nCampaign completed!")
    click.echo(f"Results: {len(results.get('tasks', {}))} tasks finished")
    click.echo(f"\nFor better control, use: deepr prep plan / deepr prep execute")


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
    import os

    # Determine provider based on model
    is_deep_research = "deep-research" in model.lower()
    if is_deep_research:
        provider = os.getenv("DEEPR_DEEP_RESEARCH_PROVIDER", "openai")
    else:
        provider = os.getenv("DEEPR_DEFAULT_PROVIDER", "xai")

    # Execute team research
    await run_dream_team(question, model, perspectives, provider=provider)


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
@click.option("--provider", "-p", default="openai", type=click.Choice(["openai", "azure", "gemini", "grok"]))
@click.option("--no-web", is_flag=True)
@click.option("--no-code", is_flag=True)
@click.option("--upload", "-u", multiple=True)
@click.option("--limit", "-l", type=float)
@click.option("--yes", "-y", is_flag=True)
def run_alias(query, model, provider, no_web, no_code, upload, limit, yes):
    """Quick alias for 'deepr run focus' - run a focused research job."""
    asyncio.run(_run_single(query, model, provider, no_web, no_code, upload, limit, yes))


if __name__ == "__main__":
    run()
