"""Run research jobs with modern CLI interface."""

import click
import asyncio
import os
import time
from pathlib import Path
from typing import Optional, List
from deepr.queue.local_queue import SQLiteQueue
from deepr.queue.base import ResearchJob, JobStatus
from deepr.cli.commands.budget import check_budget_approval
from deepr.cli.colors import console, print_success, print_error, print_warning
from deepr.cli.output import (
    OutputContext, OutputMode, OutputFormatter, OperationResult, output_options
)
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
@output_options
def focus(
    query: str,
    model: str,
    provider: str,
    no_web: bool,
    no_code: bool,
    upload: tuple,
    limit: Optional[float],
    yes: bool,
    output_context: OutputContext,
):
    """Run a focused research job (quick, single-turn research).

    Examples:
        deepr run focus "Analyze AI code editor market 2025"
        deepr run focus "Latest quantum computing trends" -m o3-deep-research
        deepr run focus "Company analysis" --upload data.csv --limit 5.00
        deepr run focus "Query" --provider gemini -m gemini-2.5-flash
        deepr run focus "Latest from xAI" --provider grok -m grok-4-fast
    """
    asyncio.run(_run_single(query, model, provider, no_web, no_code, upload, limit, yes, output_context))


@run.command()
@click.argument("query")
@click.option("--model", "-m", default="o4-mini-deep-research", help="Research model to use")
@click.option("--provider", "-p", default="openai", type=click.Choice(["openai", "azure", "gemini", "grok"]), help="Research provider (openai, azure, gemini, grok)")
@click.option("--no-web", is_flag=True, help="Disable web search")
@click.option("--no-code", is_flag=True, help="Disable code interpreter")
@click.option("--upload", "-u", multiple=True, help="Upload files for context")
@click.option("--limit", "-l", type=float, help="Cost limit in dollars")
@click.option("--yes", "-y", is_flag=True, help="Skip budget confirmation")
@output_options
def single(
    query: str,
    model: str,
    provider: str,
    no_web: bool,
    no_code: bool,
    upload: tuple,
    limit: Optional[float],
    yes: bool,
    output_context: OutputContext,
):
    """[DEPRECATED: Use 'deepr run focus'] Run a single research job.

    Examples:
        deepr run single "Analyze AI code editor market 2025"
        deepr run single "Latest quantum computing trends" -m o3-deep-research
        deepr run single "Company analysis" --upload data.csv --limit 5.00
        deepr run single "Query" --provider gemini -m gemini-2.5-flash
        deepr run single "Latest from xAI" --provider grok -m grok-4-fast
    """
    if output_context.mode == OutputMode.VERBOSE:
        click.echo("[DEPRECATION] 'deepr run single' is deprecated. Use 'deepr run focus' instead.\n")
    asyncio.run(_run_single(query, model, provider, no_web, no_code, upload, limit, yes, output_context))


async def _run_single(
    query: str,
    model: str,
    provider: str,
    no_web: bool,
    no_code: bool,
    upload: tuple,
    limit: Optional[float],
    yes: bool,
    output_context: Optional[OutputContext] = None,
):
    """Execute single research job.
    
    Orchestrates the research workflow:
    1. Budget approval
    2. File uploads (if any)
    3. Job submission to queue
    4. Provider API submission
    5. Result handling
    
    Args:
        query: Research query
        model: Model to use
        provider: Provider name
        no_web: Disable web search
        no_code: Disable code interpreter
        upload: Files to upload
        limit: Cost limit
        yes: Skip confirmation
        output_context: Output formatting context (optional for backward compatibility)
    """
    # Import refactored modules
    from deepr.cli.commands.provider_factory import (
        get_api_key, create_provider_instance, get_tool_name,
        supports_background_jobs, supports_vector_stores
    )
    from deepr.cli.commands.file_handler import handle_file_uploads
    
    # Create default output context if not provided (backward compatibility)
    if output_context is None:
        output_context = OutputContext(mode=OutputMode.VERBOSE)
    
    formatter = OutputFormatter(output_context)
    start_time = time.time()
    
    # Estimate cost and show header
    estimated_cost = estimate_cost(model, enable_web_search=not no_web)
    _show_research_header(output_context, query, provider, model, estimated_cost, upload)
    
    # Start operation feedback
    formatter.start_operation(f"Researching: {query[:50]}...")

    # Budget check
    if not _check_budget(yes, estimated_cost, output_context):
        return

    # Handle file uploads using refactored module
    document_ids = []
    vector_store_id = None
    if upload:
        from deepr.config import load_config
        config = load_config()
        
        upload_result = await handle_file_uploads(
            provider, upload, formatter, config
        )
        
        # Report errors in verbose mode
        if upload_result.has_errors and output_context.mode == OutputMode.VERBOSE:
            for error in upload_result.errors:
                print_warning(error)
        
        # Extract results
        vector_store_id = upload_result.vector_store_id
        if not supports_vector_stores(provider):
            document_ids = upload_result.uploaded_ids

    # Create and enqueue job
    job_id, job = await _create_and_enqueue_job(
        query, model, provider, no_web, no_code,
        document_ids, vector_store_id, limit, upload
    )
    formatter.progress("Submitting research job...")

    # Submit to provider and handle response
    await _submit_to_provider(
        job_id, query, model, provider, no_web, no_code,
        document_ids, vector_store_id, output_context,
        formatter, start_time
    )


def _show_research_header(
    output_context: OutputContext,
    query: str,
    provider: str,
    model: str,
    estimated_cost: float,
    upload: tuple
) -> None:
    """Display research header in verbose mode."""
    if output_context.mode == OutputMode.VERBOSE:
        click.echo("\n" + "="*70)
        click.echo("  DEEPR - Single Research")
        click.echo("="*70 + "\n")
        click.echo(f"Query: {query}")
        click.echo(f"Provider: {provider}")
        click.echo(f"Model: {model}")
        click.echo(f"Estimated cost: ${estimated_cost:.2f}")
        if upload:
            click.echo(f"Files: {', '.join(upload)}")
        click.echo()


def _check_budget(yes: bool, estimated_cost: float, output_context: OutputContext) -> bool:
    """Check budget approval. Returns True if approved, False if cancelled."""
    if yes or check_budget_approval(estimated_cost):
        return True
    
    if output_context.mode == OutputMode.VERBOSE:
        if not click.confirm(f"Proceed with estimated cost ${estimated_cost:.2f}?"):
            click.echo("Cancelled.")
            return False
    
    return True


async def _create_and_enqueue_job(
    query: str,
    model: str,
    provider: str,
    no_web: bool,
    no_code: bool,
    document_ids: List[str],
    vector_store_id: Optional[str],
    limit: Optional[float],
    upload: tuple
) -> tuple:
    """Create research job and add to queue. Returns (job_id, job)."""
    # Prepare job metadata for cleanup tracking
    job_metadata = {}
    if vector_store_id:
        job_metadata["vector_store_id"] = vector_store_id
        job_metadata["cleanup_vector_store"] = True
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
    return job_id, job


async def _submit_to_provider(
    job_id: str,
    query: str,
    model: str,
    provider: str,
    no_web: bool,
    no_code: bool,
    document_ids: List[str],
    vector_store_id: Optional[str],
    output_context: OutputContext,
    formatter: OutputFormatter,
    start_time: float
) -> None:
    """Submit job to provider API and handle response."""
    from deepr.cli.commands.provider_factory import (
        create_provider_instance, get_tool_name,
        supports_background_jobs, supports_vector_stores
    )
    from deepr.providers.base import ResearchRequest, ToolConfig
    from deepr.config import load_config
    
    config = load_config()
    queue = SQLiteQueue()
    
    try:
        provider_instance = create_provider_instance(provider, config)
        
        # Build tools list using provider factory
        tools = _build_tools_list(provider, no_web, no_code, vector_store_id)
        
        # Validate tools for deep research models
        if supports_vector_stores(provider) and "deep-research" in model and not tools:
            _handle_missing_tools_error(job_id, model, formatter, start_time)
            return

        # Create and submit research request
        request = ResearchRequest(
            prompt=query,
            model=model,
            system_message="You are a research assistant. Provide comprehensive, citation-backed analysis.",
            tools=tools,
            background=supports_background_jobs(provider),
            document_ids=document_ids if document_ids else None,
        )
        
        provider_job_id = await provider_instance.submit_research(request)
        
        # Handle response based on provider type
        if supports_background_jobs(provider):
            await _handle_background_job(
                job_id, provider_job_id, output_context, queue
            )
        else:
            await _handle_immediate_job(
                job_id, provider_job_id, query, model, provider_instance,
                output_context, formatter, start_time, config, queue
            )

    except Exception as e:
        duration = time.time() - start_time
        result = OperationResult(
            success=False,
            duration_seconds=duration,
            cost_usd=0.0,
            job_id=job_id,
            error=f"Failed to submit to provider: {e}",
            error_code="PROVIDER_ERROR"
        )
        formatter.complete(result)


def _build_tools_list(
    provider: str,
    no_web: bool,
    no_code: bool,
    vector_store_id: Optional[str]
) -> List:
    """Build provider-specific tools list."""
    from deepr.cli.commands.provider_factory import get_tool_name, supports_vector_stores
    from deepr.providers.base import ToolConfig
    
    tools = []
    if not no_web:
        tool_name = get_tool_name(provider, "web_search")
        tools.append(ToolConfig(type=tool_name))
    if not no_code:
        tools.append(ToolConfig(type="code_interpreter"))
    
    # Add file_search tool when vector store is available
    if vector_store_id and supports_vector_stores(provider):
        tools.append(ToolConfig(
            type="file_search",
            vector_store_ids=[vector_store_id]
        ))
    
    return tools


def _handle_missing_tools_error(
    job_id: str,
    model: str,
    formatter: OutputFormatter,
    start_time: float
) -> None:
    """Handle error when deep research model has no tools."""
    duration = time.time() - start_time
    result = OperationResult(
        success=False,
        duration_seconds=duration,
        cost_usd=0.0,
        job_id=job_id,
        error=f"{model} requires at least one tool (web search, code interpreter, or file upload)",
        error_code="MISSING_TOOLS"
    )
    formatter.complete(result)


async def _handle_background_job(
    job_id: str,
    provider_job_id: str,
    output_context: OutputContext,
    queue: SQLiteQueue
) -> None:
    """Handle OpenAI/Azure background job submission."""
    await queue.update_status(
        job_id=job_id,
        status=JobStatus.PROCESSING,
        provider_job_id=provider_job_id
    )
    
    if output_context.mode == OutputMode.VERBOSE:
        click.echo(f"\nJob submitted: {job_id[:12]}")
        click.echo(f"Provider job ID: {provider_job_id}")
        click.echo(f"\nCheck status: deepr status {job_id[:12]}")
        click.echo(f"View results: deepr get {job_id[:12]}")
        click.echo(f"List all jobs: deepr list")
    elif output_context.mode == OutputMode.JSON:
        import json as json_module
        print(json_module.dumps({
            "status": "pending",
            "job_id": job_id,
            "provider_job_id": provider_job_id
        }))


async def _handle_immediate_job(
    job_id: str,
    provider_job_id: str,
    query: str,
    model: str,
    provider_instance,
    output_context: OutputContext,
    formatter: OutputFormatter,
    start_time: float,
    config: dict,
    queue: SQLiteQueue
) -> None:
    """Handle Gemini/Grok immediate job completion."""
    response = await provider_instance.get_status(provider_job_id)
    
    if response.status == "completed":
        # Extract and save content
        content = _extract_response_content(response)
        
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
        
        # Update queue
        await queue.update_status(job_id, JobStatus.COMPLETED)
        actual_cost = response.usage.cost if response.usage and response.usage.cost else 0.0
        if response.usage and response.usage.cost:
            await queue.update_results(
                job_id,
                report_paths={"markdown": report_metadata.url},
                cost=response.usage.cost,
                tokens_used=response.usage.total_tokens
            )
        
        # Output result
        duration = time.time() - start_time
        result = OperationResult(
            success=True,
            duration_seconds=duration,
            cost_usd=actual_cost,
            report_path=str(report_metadata.url),
            job_id=job_id
        )
        formatter.complete(result)
    else:
        # Still processing
        await queue.update_status(
            job_id=job_id,
            status=JobStatus.PROCESSING,
            provider_job_id=provider_job_id
        )
        if output_context.mode == OutputMode.VERBOSE:
            click.echo(f"\nJob submitted: {job_id[:12]}")
            click.echo(f"Provider job ID: {provider_job_id}")
        elif output_context.mode == OutputMode.JSON:
            import json as json_module
            print(json_module.dumps({
                "status": "pending",
                "job_id": job_id,
                "provider_job_id": provider_job_id
            }))


def _extract_response_content(response) -> str:
    """Extract text content from provider response."""
    content = ""
    if response.output:
        for block in response.output:
            if block.get('type') == 'message':
                for item in block.get('content', []):
                    if item.get('type') in ['output_text', 'text']:
                        text = item.get('text', '')
                        if text:
                            content += text + "\n"
    return content


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
@output_options
def docs(
    topic: str,
    model: str,
    provider: str,
    upload: tuple,
    limit: Optional[float],
    yes: bool,
    output_context: OutputContext,
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
        yes=yes,
        output_context=output_context
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
@output_options
def run_alias(query, model, provider, no_web, no_code, upload, limit, yes, output_context):
    """Quick alias for 'deepr run focus' - run a focused research job."""
    asyncio.run(_run_single(query, model, provider, no_web, no_code, upload, limit, yes, output_context))


if __name__ == "__main__":
    run()
