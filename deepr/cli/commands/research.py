# research.py
"""Research commands - submit and manage individual research jobs."""

import os

import click

from deepr.cli.colors import console, print_error, print_section_header, print_success, print_warning

# from deepr.services.cost_estimation import CostEstimator  # TODO: implement or remove

# -------------------------------
# Helpers
# -------------------------------


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


async def _resolve_job_id(queue, maybe_prefix: str):
    """Allow users to pass a short prefix (first 8 chars). Falls back to exact match."""
    if len(maybe_prefix) >= 32:  # likely a full UUID
        job = await queue.get_job(maybe_prefix)
        return job.id if job else None

    # naive prefix scan; optimize in queue layer if needed
    jobs = await queue.list_jobs(limit=500)  # implement list_jobs in queue if missing
    for j in jobs:
        if j.id.startswith(maybe_prefix):
            return j.id
    return None


@click.group()
def research():
    """Submit and manage research jobs."""
    pass


@research.command()
@click.argument("prompt")
@click.option(
    "--provider",
    "-P",
    default=None,
    type=click.Choice(["openai", "azure", "gemini", "grok"]),
    help="Research provider (default: from config or 'openai')",
)
@click.option(
    "--model",
    "-m",
    default="o4-mini-deep-research",
    type=click.Choice(["o4-mini-deep-research", "o3-deep-research"]),
    help="Deep research model (o4-mini faster/cheaper, o3 more comprehensive)",
)
@click.option("--priority", "-p", default=3, type=click.IntRange(1, 5), help="Priority (1=high, 5=low)")
@click.option("--web-search/--no-web-search", default=True, help="Enable web search (default: enabled)")
@click.option("--cost-limit", type=float, default=None, help="Override max cost for this job (USD)")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.option("--auto-select", is_flag=True, help="Use autonomous provider router for selection")
@click.option(
    "--entropy-threshold",
    type=float,
    default=None,
    help="Entropy threshold for stopping (0.0-1.0, lower = stop earlier)",
)
@click.option("--token-budget", type=int, default=None, help="Token budget for context management")
@click.option(
    "--research-mode",
    type=click.Choice(["read_only", "standard", "extended", "unrestricted"]),
    default="standard",
    help="Research mode controlling tool access",
)
@click.option("--context", "context_job_id", default=None, help="Use prior research as context (job ID or prefix)")
@click.option("--no-context-discovery", is_flag=True, help="Disable automatic related research detection")
def submit(
    prompt: str,
    provider: str,
    model: str,
    priority: int,
    web_search: bool,
    cost_limit: float,
    yes: bool,
    auto_select: bool,
    entropy_threshold: float,
    token_budget: int,
    research_mode: str,
    context_job_id: str,
    no_context_discovery: bool,
):
    """Submit a deep research job."""
    print_section_header("Submit Deep Research Job")

    # Resolve provider from config if not specified
    from deepr.config import load_config

    config = load_config()

    # Use autonomous provider router if requested or no provider specified
    if auto_select or (provider is None and model is None):
        try:
            from deepr.observability.provider_router import AutonomousProviderRouter

            router = AutonomousProviderRouter()
            resolved_provider, resolved_model = router.select_provider(task_type="research")
            # Only use router selection if user didn't specify
            if provider is None:
                provider = resolved_provider
            if model == "o4-mini-deep-research":  # default value
                model = resolved_model if resolved_model in ["o4-mini-deep-research", "o3-deep-research"] else model
            console.print(f"[dim]Provider router selected: {resolved_provider}/{resolved_model}[/dim]")
        except Exception:
            pass  # Fall back to config

    resolved_provider = provider or config.get("provider", "openai")

    click.echo("\nConfiguration:")
    click.echo(f"   Provider: {resolved_provider}")
    click.echo(f"   Model: {model}")
    click.echo(f"   Priority: {priority} ({'high' if priority <= 2 else 'normal' if priority <= 4 else 'low'})")
    click.echo(f"   Web Search: {'enabled' if web_search else 'disabled'}")
    click.echo(f"   Research Mode: {research_mode}")
    if entropy_threshold is not None:
        click.echo(f"   Entropy Threshold: {entropy_threshold}")
    if token_budget is not None:
        click.echo(f"   Token Budget: {token_budget:,}")
    click.echo(f"   Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}")

    # Context discovery (6.1, 6.2, 6.3)
    context_content = None
    related_found = []

    # Handle explicit context (6.3)
    if context_job_id:
        from deepr.services.context_index import ContextIndex

        index = ContextIndex()
        context_result = index.get_report_by_job_id(context_job_id)

        if not context_result:
            print_error(f"Context not found: {context_job_id}")
            console.print("[dim]Run 'deepr search index' to index reports first[/dim]")
            raise click.Abort()

        # Check for stale context
        if index.check_stale_context(context_job_id, max_age_days=30):
            print_warning("Context is >30 days old. Findings may be outdated.")
            if not yes and not click.confirm("Use this context anyway?"):
                print_warning("Cancelled")
                return

        context_content = index.get_report_content(context_job_id)
        if context_content:
            console.print("\n[cyan]Using context from prior research:[/cyan]")
            console.print(f"   {context_result.prompt[:60]}{'...' if len(context_result.prompt) > 60 else ''}")
            console.print(f"   [dim]{context_result.created_at.strftime('%Y-%m-%d')} | {context_result.model}[/dim]")

            # Show cost savings estimate
            from deepr.providers.registry import get_cost_estimate

            prior_cost = get_cost_estimate(context_result.model or model)
            console.print(f"   [green]Estimated savings: ${prior_cost:.2f} by reusing prior research[/green]")

    # Automatic context discovery (6.1, 6.2)
    elif not no_context_discovery:
        try:
            import asyncio

            from deepr.services.context_index import ContextIndex

            index = ContextIndex()
            stats = index.get_stats()

            if stats["indexed_reports"] > 0:
                related_found = asyncio.run(index.find_related(prompt, top_k=3, threshold=0.75))

                if related_found:
                    console.print(f"\n[cyan]Related prior research found ({len(related_found)}):[/cyan]")
                    for i, result in enumerate(related_found, 1):
                        score_color = "green" if result.similarity >= 0.85 else "yellow"
                        console.print(
                            f"   {i}. [{score_color}]{result.similarity:.0%}[/{score_color}] {result.prompt[:50]}..."
                        )
                        console.print(
                            f"      [dim]{result.job_id[:8]} | {result.created_at.strftime('%Y-%m-%d')}[/dim]"
                        )

                    console.print(f"\n[dim]Use --context {related_found[0].job_id[:8]} to include as context[/dim]")

        except Exception as e:
            # Don't fail on context discovery errors
            console.print(f"[dim]Context discovery skipped: {e}[/dim]")

    if not yes and not click.confirm("\nSubmit deep research job?"):
        print_warning("Cancelled")
        return

    print_success("Submitting job...")

    try:
        import asyncio
        import uuid
        from datetime import datetime

        # Initialize metadata emitter for tracing
        from deepr.observability.metadata import MetadataEmitter
        from deepr.providers import create_provider
        from deepr.providers.base import ResearchRequest, ToolConfig
        from deepr.queue import create_queue
        from deepr.queue.base import JobStatus, ResearchJob

        emitter = MetadataEmitter()
        op = emitter.start_task(
            "research_submit",
            prompt=prompt,
            attributes={"provider": resolved_provider, "model": model, "web_search": web_search},
        )

        db_path = config.get("queue_db_path", "queue/research_queue.db")
        _ensure_parent_dir(db_path)

        queue = create_queue("local", db_path=db_path)

        # Get provider-specific API key
        if resolved_provider == "gemini":
            api_key = config.get("gemini_api_key")
        elif resolved_provider in ["grok", "xai"]:
            api_key = config.get("xai_api_key")
        elif resolved_provider == "azure":
            api_key = config.get("azure_api_key")
        else:  # openai
            api_key = config.get("api_key")

        provider_instance = create_provider(resolved_provider, api_key=api_key)

        job_id = str(uuid.uuid4())

        # Build metadata with new options
        job_metadata = {
            "research_mode": research_mode,
        }
        if entropy_threshold is not None:
            job_metadata["entropy_threshold"] = entropy_threshold
        if token_budget is not None:
            job_metadata["token_budget"] = token_budget
        if context_job_id:
            job_metadata["context_from_job"] = context_job_id
        if related_found:
            job_metadata["related_research_detected"] = [r.job_id for r in related_found[:3]]

        job = ResearchJob(
            id=job_id,
            prompt=prompt,
            model=model,
            provider=resolved_provider,
            status=JobStatus.QUEUED,
            priority=priority,
            submitted_at=datetime.utcnow(),
            cost_limit=cost_limit if cost_limit is not None else config.get("max_cost_per_job", 10.0),
            enable_web_search=web_search,
            metadata=job_metadata,
        )

        async def submit_job():
            await queue.enqueue(job)

            # Use provider-specific tool names
            tools = []
            if web_search:
                tool_name = "web_search" if resolved_provider in ["grok", "xai"] else "web_search_preview"
                tools.append(ToolConfig(type=tool_name))

            # Build the prompt with optional context (6.3)
            research_prompt = prompt
            if context_content:
                research_prompt = (
                    f"## Prior Research Context\n\n"
                    f"The following prior research may be relevant. Use it as background "
                    f"but verify and update any findings:\n\n"
                    f"---\n{context_content}\n---\n\n"
                    f"## New Research Query\n\n{prompt}"
                )

            request = ResearchRequest(
                prompt=research_prompt,
                model=model,
                system_message=(
                    "You are a helpful AI research assistant. Provide comprehensive, "
                    "well-researched responses with inline citations."
                ),
                tools=tools,
                background=True if resolved_provider in ["openai", "azure"] else False,
            )
            provider_job_id = await provider_instance.submit_research(request)
            await queue.update_status(job_id=job_id, status=JobStatus.PROCESSING, provider_job_id=provider_job_id)
            return provider_job_id

        provider_job_id = asyncio.run(submit_job())

        # Complete metadata tracking
        op.set_model(model, resolved_provider)
        op.set_attribute("job_id", job_id)
        op.set_attribute("provider_job_id", provider_job_id)
        emitter.complete_task(op)

        # Save trace for later analysis
        from pathlib import Path

        trace_path = Path(f"data/traces/submit_{job_id[:8]}.json")
        emitter.save_trace(trace_path)

        print_success("Job submitted successfully!")
        console.print(f"\nJob ID: {job_id}")
        console.print(f"Provider Job ID: {provider_job_id}")
        console.print("\nNext steps:")
        console.print(f"   deepr research wait {job_id[:8]}  (prefix OK)")
        console.print(f"   deepr research status {job_id[:8]}")

    except Exception as e:
        # Record failure in metadata
        try:
            emitter.fail_task(op, str(e))
        except Exception:
            pass
        print_error(f"Error: {e}")
        raise click.Abort()


@research.command()
@click.argument("job_id")
def status(job_id: str):
    """Check status of a research job."""
    print_section_header(f"Job Status: {job_id[:8]}...")

    try:
        import asyncio

        from deepr.config import load_config
        from deepr.queue import create_queue
        from deepr.queue.base import JobStatus

        config = load_config()
        db_path = config.get("queue_db_path", "queue/research_queue.db")
        _ensure_parent_dir(db_path)
        queue = create_queue("local", db_path=db_path)

        async def get_status():
            full_id = await _resolve_job_id(queue, job_id)
            if not full_id:
                return None
            return await queue.get_job(full_id)

        job = asyncio.run(get_status())
        if not job:
            print_error(f"Job not found: {job_id}")
            raise click.Abort()

        console.print(f"\nStatus: {job.status.name}")
        console.print("\nDetails:")
        console.print(f"   ID: {job.id}")
        console.print(f"   Model: {job.model}")
        console.print(f"   Priority: {job.priority}")
        console.print(f"   Submitted: {job.submitted_at}")
        if getattr(job, "started_at", None):
            console.print(f"   Started: {job.started_at}")
        if getattr(job, "completed_at", None):
            console.print(f"   Completed: {job.completed_at}")
        if getattr(job, "cost", None) is not None:
            console.print(f"   Cost: ${job.cost:.4f}")
        if getattr(job, "tokens_used", None):
            console.print(f"   Tokens: {job.tokens_used:,}")

        console.print("\nPrompt:")
        console.print(f"   {job.prompt}")

        if job.status is JobStatus.COMPLETED:
            console.print(f"\nView result: deepr research result {job.id[:8]}")
        elif job.status is JobStatus.PROCESSING:
            console.print("\nJob is still processing...")
        elif job.status is JobStatus.FAILED and getattr(job, "last_error", None):
            console.print(f"\nError: {job.last_error}")

    except Exception as e:
        print_error(f"Error: {e}")
        raise click.Abort()


@research.command()
@click.argument("job_id")
def result(job_id: str):
    """View result of a completed research job."""
    print_section_header(f"Research Result: {job_id[:8]}...")

    try:
        import asyncio

        from deepr.config import load_config
        from deepr.providers import create_provider
        from deepr.queue import create_queue
        from deepr.queue.base import JobStatus

        config = load_config()
        db_path = config.get("queue_db_path", "queue/research_queue.db")
        _ensure_parent_dir(db_path)
        queue = create_queue("local", db_path=db_path)
        provider = create_provider(config.get("provider", "openai"), api_key=config.get("api_key"))

        async def get_result():
            full_id = await _resolve_job_id(queue, job_id)
            if not full_id:
                return None, None
            job = await queue.get_job(full_id)
            if not job or job.status is not JobStatus.COMPLETED:
                return job, None
            if job.provider_job_id:
                resp = await provider.get_status(job.provider_job_id)
                return job, resp
            return job, None

        job, response = asyncio.run(get_result())
        if not job:
            print_error(f"Job not found: {job_id}")
            raise click.Abort()

        if not response:
            print_error("Result not available yet")
            console.print(f"Status: {job.status.name}")
            console.print(f"\nCheck status: deepr research status {job_id[:8]}")
            raise click.Abort()

        print_success("Research Report:")
        console.print()
        if getattr(response, "output", None):
            for block in response.output:
                if block.get("type") == "message":
                    for content in block.get("content", []):
                        text = content.get("text", "")
                        if text:
                            console.print(text)
                    if content := block.get("content"):
                        anns = next((c.get("annotations", []) for c in content if "annotations" in c), [])
                        if anns:
                            console.print(f"\n\nCitations ({len(anns)}):")
                            for i, ann in enumerate(anns, 1):
                                console.print(f"   [{i}] {ann.get('title', 'Untitled')}")
                                if ann.get("url"):
                                    console.print(f"       {ann['url']}")

        if getattr(response, "usage", None):
            u = response.usage
            console.print("\n\nUsage:")
            if hasattr(u, "input_tokens"):
                console.print(f"   Input tokens: {u.input_tokens:,}")
            if hasattr(u, "output_tokens"):
                console.print(f"   Output tokens: {u.output_tokens:,}")
            if hasattr(u, "total_tokens"):
                console.print(f"   Total tokens: {u.total_tokens:,}")
            if hasattr(u, "cost"):
                console.print(f"   Cost: ${u.cost:.4f}")

    except Exception as e:
        print_error(f"Error: {e}")
        raise click.Abort()


@research.command()
@click.argument("job_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def cancel(job_id: str, yes: bool):
    """Cancel a research job."""
    print_section_header(f"Cancel Job: {job_id[:8]}...")

    try:
        import asyncio

        from deepr.config import load_config
        from deepr.providers import create_provider
        from deepr.queue import create_queue
        from deepr.queue.base import JobStatus

        config = load_config()
        db_path = config.get("queue_db_path", "queue/research_queue.db")
        _ensure_parent_dir(db_path)
        queue = create_queue("local", db_path=db_path)
        provider = create_provider(config.get("provider", "openai"), api_key=config.get("api_key"))

        async def cancel_job():
            full_id = await _resolve_job_id(queue, job_id)
            if not full_id:
                return None, "Job not found"
            job = await queue.get_job(full_id)
            if not job:
                return None, "Job not found"
            if job.status is JobStatus.COMPLETED:
                return job, "Job already completed"
            if job.status is JobStatus.FAILED:
                return job, "Job already failed"
            return job, None

        job, error = asyncio.run(cancel_job())
        if error:
            print_error(error)
            raise click.Abort()

        console.print("\nJob Details:")
        console.print(f"   ID: {job.id}")
        console.print(f"   Status: {job.status.name}")
        console.print(f"   Prompt: {job.prompt[:80]}{'...' if len(job.prompt) > 80 else ''}")
        if job.provider_job_id:
            console.print(f"   Provider Job ID: {job.provider_job_id}")

        if not yes and not click.confirm("\nCancel this job?"):
            print_warning("Cancelled")
            return

        print_success("Cancelling job...")

        async def do_cancel():
            if job.provider_job_id:
                try:
                    await provider.cancel_job(job.provider_job_id)
                    console.print("[success]Cancelled at provider[/success]")
                except Exception as e:
                    console.print(f"   Warning: Could not cancel at provider: {e}")
            await queue.update_status(job_id=job.id, status=JobStatus.FAILED, error="Cancelled by user")

        import asyncio as _asyncio

        _asyncio.run(do_cancel())
        print_success("Job cancelled successfully!")

    except Exception as e:
        print_error(f"Error: {e}")
        raise click.Abort()


@research.command()
@click.argument("job_id")
@click.option("--timeout", "-t", default=300, help="Timeout in seconds (default: 300)")
@click.option("--progress", "-p", is_flag=True, help="Show real-time progress with phase tracking")
@click.option("--poll-interval", default=5, help="Poll interval in seconds (default: 5)")
def wait(job_id: str, timeout: int, progress: bool, poll_interval: int):
    """Wait for a job to complete and show result.

    Use --progress for real-time phase tracking with progress bar.
    """
    import asyncio
    import time

    from deepr.config import load_config
    from deepr.providers import create_provider
    from deepr.queue import create_queue
    from deepr.queue.base import JobStatus

    print_section_header(f"Waiting for Job: {job_id[:8]}...")

    try:
        config = load_config()
        db_path = config.get("queue_db_path", "queue/research_queue.db")
        _ensure_parent_dir(db_path)
        queue = create_queue("local", db_path=db_path)
        provider = create_provider(config.get("provider", "openai"), api_key=config.get("api_key"))

        start_time = time.time()

        async def get_job_info():
            full_id = await _resolve_job_id(queue, job_id)
            if not full_id:
                return None, None
            job = await queue.get_job(full_id)
            return full_id, job

        full_id, job = asyncio.run(get_job_info())
        if not job:
            print_error(f"Job not found: {job_id}")
            raise click.Abort()

        # Use real-time progress tracker if requested and we have a provider job ID
        if progress and job.provider_job_id:
            from deepr.cli.realtime_progress import ResearchProgressTracker

            async def track_with_progress():
                tracker = ResearchProgressTracker(provider)
                try:
                    response = await tracker.track_job(
                        job_id=job.provider_job_id,
                        poll_interval=poll_interval,
                        timeout=timeout,
                        show_partial=True,
                    )
                    return job, response
                except TimeoutError:
                    return job, "Timeout"
                except Exception as e:
                    return job, f"Error: {e}"

            job, response = asyncio.run(track_with_progress())
        else:
            # Fallback to simple polling
            check_interval = poll_interval

            async def wait_for_completion():
                while True:
                    elapsed = time.time() - start_time
                    if elapsed > timeout:
                        return job, "Timeout"
                    updated_job = await queue.get_job(full_id)
                    if not updated_job:
                        return None, "Job not found"
                    if updated_job.status is JobStatus.COMPLETED:
                        if updated_job.provider_job_id:
                            resp = await provider.get_status(updated_job.provider_job_id)
                            return updated_job, resp
                        return updated_job, None
                    if updated_job.status is JobStatus.FAILED:
                        return updated_job, "Job failed"
                    click.echo(f"  [{int(elapsed)}s] Status: {updated_job.status.name}...")
                    await asyncio.sleep(check_interval)

            job, response = asyncio.run(wait_for_completion())

        if not job:
            print_error(response if isinstance(response, str) else "Job not found")
            raise click.Abort()
        if response == "Timeout":
            print_error(f"Timeout after {timeout}s")
            raise click.Abort()
        if response == "Job failed" or (isinstance(response, str) and response.startswith("Error:")):
            print_error(response if isinstance(response, str) else "Job failed")
            # Record failure with provider router
            try:
                from deepr.observability.provider_router import AutonomousProviderRouter

                router = AutonomousProviderRouter()
                router.record_result(
                    provider=getattr(job, "provider", "openai"),
                    model=job.model,
                    success=False,
                    error=getattr(job, "last_error", "Unknown error"),
                )
            except Exception:
                pass
            if getattr(job, "last_error", None):
                console.print(f"Error: {job.last_error}")
            raise click.Abort()
        if not response:
            print_error("Result not available")
            raise click.Abort()

        print_success("Job completed!")

        # Record result with provider router for metrics
        try:
            from deepr.observability.provider_router import AutonomousProviderRouter

            router = AutonomousProviderRouter()
            elapsed_ms = (time.time() - start_time) * 1000
            cost = getattr(getattr(response, "usage", None), "cost", 0.0) if response else 0.0
            router.record_result(
                provider=getattr(job, "provider", "openai"),
                model=job.model,
                success=True,
                latency_ms=elapsed_ms,
                cost=cost,
            )
        except Exception:
            pass  # Don't fail on metrics recording

        console.print()
        if getattr(response, "output", None):
            for block in response.output:
                if block.get("type") == "message":
                    for content in block.get("content", []):
                        text = content.get("text", "")
                        if text:
                            console.print(text)
        if getattr(response, "usage", None):
            u = response.usage
            console.print(f"\n\nCost: ${getattr(u, 'cost', 0.0):.4f} | Tokens: {getattr(u, 'total_tokens', 0):,}")

    except Exception as e:
        print_error(f"Error: {e}")
        raise click.Abort()


@research.command()
@click.argument("job_id")
@click.option("--explain", "--why", is_flag=True, help="Show research path reasoning")
@click.option("--timeline", is_flag=True, help="Show reasoning evolution timeline")
@click.option("--temporal", is_flag=True, help="Show temporal knowledge timeline with findings/hypotheses")
@click.option("--lineage", is_flag=True, help="Show context lineage (which sources informed which tasks)")
@click.option("--full-trace", is_flag=True, help="Export complete audit trail")
@click.option("--output", "-o", type=click.Path(), help="Output file for full trace export")
@click.option("--show-budget", is_flag=True, help="Show token budget utilization")
def trace(
    job_id: str,
    explain: bool,
    timeline: bool,
    temporal: bool,
    lineage: bool,
    full_trace: bool,
    output: str,
    show_budget: bool,
):
    """View trace information for a research job.

    Examples:
        deepr research trace abc123 --explain
        deepr research trace abc123 --timeline
        deepr research trace abc123 --temporal
        deepr research trace abc123 --lineage
        deepr research trace abc123 --full-trace -o trace.json
        deepr research trace abc123 --show-budget
    """
    from pathlib import Path

    from rich.panel import Panel
    from rich.table import Table

    print_section_header(f"Trace: {job_id[:8]}...")

    # Find trace file
    trace_dir = Path("data/traces")
    trace_files = list(trace_dir.glob(f"*{job_id[:8]}*.json"))

    if not trace_files:
        print_error(f"No trace found for job {job_id}")
        console.print(f"\n[dim]Traces are saved in {trace_dir}[/dim]")
        return

    trace_path = trace_files[0]

    try:
        from deepr.observability.metadata import MetadataEmitter

        emitter = MetadataEmitter.load_trace(trace_path)

        if explain:
            # Show research path reasoning
            console.print(
                Panel(
                    f"[bold]Research Path Explanation[/bold]\n\n"
                    f"Trace ID: {emitter.trace_context.trace_id}\n"
                    f"Total Tasks: {len(emitter.tasks)}\n"
                    f"Total Cost: ${emitter.get_total_cost():.4f}",
                    title="Research Path",
                )
            )

            # Show task hierarchy
            console.print("\n[bold]Task Hierarchy:[/bold]")
            for task in emitter.tasks:
                indent = "  " if task.parent_task_id else ""
                status_icon = "✓" if task.status == "completed" else "✗" if task.status == "failed" else "○"
                console.print(
                    f"{indent}[{'green' if task.status == 'completed' else 'red'}]{status_icon}[/] {task.task_type}"
                )
                if task.model:
                    console.print(f"{indent}   Model: {task.model}")
                if task.cost > 0:
                    console.print(f"{indent}   Cost: ${task.cost:.4f}")
                if task.context_sources:
                    console.print(f"{indent}   Sources: {len(task.context_sources)}")

        if timeline:
            # Show reasoning evolution timeline
            timeline_data = emitter.get_timeline()

            table = Table(title="Reasoning Timeline")
            table.add_column("Time", style="dim")
            table.add_column("Task", style="cyan")
            table.add_column("Status")
            table.add_column("Duration", justify="right")
            table.add_column("Cost", justify="right")

            for entry in timeline_data:
                start = entry["start_time"][:19].replace("T", " ")
                status_color = "green" if entry["status"] == "completed" else "red"
                duration = f"{entry['duration_ms']:.0f}ms" if entry.get("duration_ms") else "-"
                cost = f"${entry['cost']:.4f}" if entry.get("cost", 0) > 0 else "-"

                table.add_row(
                    start, entry["task_type"], f"[{status_color}]{entry['status']}[/{status_color}]", duration, cost
                )

            console.print(table)

            # Cost breakdown
            breakdown = emitter.get_cost_breakdown()
            if breakdown:
                console.print("\n[bold]Cost Breakdown:[/bold]")
                for task_type, cost in sorted(breakdown.items(), key=lambda x: x[1], reverse=True):
                    console.print(f"  {task_type}: ${cost:.4f}")

        if temporal:
            # Show temporal knowledge timeline
            _render_temporal_timeline(job_id, trace_path)

        if lineage:
            # Show context lineage visualization
            _render_context_lineage(emitter)

        if show_budget:
            # Show token budget utilization
            _render_budget_utilization(emitter)

        if full_trace:
            # Export complete audit trail
            output_path = Path(output) if output else Path(f"trace_{job_id[:8]}_export.json")
            emitter.save_trace(output_path)
            print_success(f"Full trace exported to {output_path}")
            console.print(
                f"\n[dim]Contains {len(emitter.tasks)} tasks and {len(emitter.trace_context.spans)} spans[/dim]"
            )

        if not (explain or timeline or temporal or lineage or full_trace or show_budget):
            # Default: show summary
            console.print(
                Panel(
                    f"[bold]Trace Summary[/bold]\n\n"
                    f"Trace ID: {emitter.trace_context.trace_id}\n"
                    f"Tasks: {len(emitter.tasks)}\n"
                    f"Spans: {len(emitter.trace_context.spans)}\n"
                    f"Total Cost: ${emitter.get_total_cost():.4f}\n\n"
                    f"Use --explain, --timeline, --temporal, --lineage, --show-budget, or --full-trace for details",
                    title="Trace Info",
                )
            )

    except Exception as e:
        print_error(f"Error loading trace: {e}")
        raise click.Abort()


def _render_temporal_timeline(job_id: str, trace_path):
    """Render temporal knowledge timeline.

    Args:
        job_id: Job identifier
        trace_path: Path to trace file
    """
    import json

    from rich.table import Table

    try:
        # Try to load temporal data from trace
        with open(trace_path, "r") as f:
            trace_data = json.load(f)

        temporal_data = trace_data.get("temporal", {})
        findings = temporal_data.get("findings", [])
        hypotheses = temporal_data.get("hypotheses", {})

        if not findings and not hypotheses:
            console.print("[dim]No temporal knowledge data found in trace.[/dim]")
            console.print("[dim]Temporal tracking requires the TemporalKnowledgeTracker to be enabled.[/dim]")
            return

        # Render findings timeline
        if findings:
            table = Table(title="Temporal Findings Timeline")
            table.add_column("Time", style="dim", width=10)
            table.add_column("Phase", justify="center", width=6)
            table.add_column("Type", style="cyan", width=12)
            table.add_column("Finding", width=50)
            table.add_column("Conf", justify="right", width=6)

            for finding in findings[:20]:  # Limit to 20 most recent
                time_str = finding.get("timestamp", "")[:10]
                phase = str(finding.get("phase", "?"))
                ftype = finding.get("finding_type", "unknown")
                text = finding.get("text", "")[:50]
                if len(finding.get("text", "")) > 50:
                    text += "..."
                conf = f"{finding.get('confidence', 0):.2f}"

                # Color code by type
                type_colors = {
                    "fact": "blue",
                    "observation": "cyan",
                    "inference": "yellow",
                    "hypothesis": "magenta",
                    "contradiction": "red",
                    "confirmation": "green",
                }
                color = type_colors.get(ftype, "white")

                table.add_row(time_str, phase, f"[{color}]{ftype}[/{color}]", text, conf)

            console.print(table)

        # Render hypothesis evolution
        if hypotheses:
            console.print("\n[bold]Hypothesis Evolution:[/bold]")

            for h_id, h_data in hypotheses.items():
                status = h_data.get("current_state", {}).get("confidence", 0)
                status_color = "green" if status > 0.5 else "yellow" if status > 0 else "red"
                status_text = "ACTIVE" if status > 0 else "INVALIDATED"

                console.print(f"\n[bold]{h_id}[/bold] [{status_color}]{status_text}[/{status_color}]")
                console.print(f"  Current: {h_data.get('current_state', {}).get('text', 'N/A')[:60]}...")
                console.print(f"  Confidence: {status:.2f}")
                console.print(f"  Evolutions: {len(h_data.get('evolution_history', []))}")

    except json.JSONDecodeError:
        console.print("[red]Error: Could not parse trace file.[/red]")
    except Exception as e:
        console.print(f"[red]Error rendering temporal timeline: {e}[/red]")


def _render_budget_utilization(emitter):
    """Render token budget utilization from trace.

    Args:
        emitter: MetadataEmitter with trace data
    """

    console.print("\n[bold]Token Budget Utilization:[/bold]\n")

    # Get token usage from tasks
    total_tokens = 0
    phase_tokens = {}

    for task in emitter.tasks:
        tokens = task.attributes.get("tokens_used", 0)
        total_tokens += tokens

        phase = task.attributes.get("phase", "unknown")
        if phase not in phase_tokens:
            phase_tokens[phase] = 0
        phase_tokens[phase] += tokens

    # Show budget bar
    from deepr.core.constants import TOKEN_BUDGET_DEFAULT

    budget = TOKEN_BUDGET_DEFAULT

    used_pct = min(total_tokens / budget * 100, 100)
    bar_width = 40
    filled = int(used_pct / 100 * bar_width)

    color = "green" if used_pct < 70 else "yellow" if used_pct < 90 else "red"
    bar = f"[{color}]{'█' * filled}[/{color}]{'░' * (bar_width - filled)}"

    console.print(f"Total Budget: {bar} {total_tokens:,} / {budget:,} ({used_pct:.1f}%)")

    # Phase breakdown
    if phase_tokens:
        console.print("\n[bold]By Phase:[/bold]")
        for phase, tokens in sorted(phase_tokens.items()):
            pct = tokens / max(total_tokens, 1) * 100
            console.print(f"  Phase {phase}: {tokens:,} tokens ({pct:.1f}%)")


def _render_context_lineage(emitter):
    """Render context lineage visualization.

    Shows which sources informed which tasks, visualizing the flow
    of information through the research process.

    Args:
        emitter: MetadataEmitter with trace data
    """
    from rich.tree import Tree

    lineage = emitter.get_context_lineage()

    if not lineage:
        console.print("[dim]No context lineage data found.[/dim]")
        console.print("[dim]Context sources are recorded when research uses prior findings or documents.[/dim]")
        return

    console.print("\n[bold]Context Lineage:[/bold]")
    console.print("[dim]Shows which sources informed each task[/dim]\n")

    # Build a tree visualization
    tree = Tree("[bold cyan]Research Flow[/bold cyan]")

    # Group tasks by their relationship
    task_map = {task.task_id: task for task in emitter.tasks}

    for task_id, sources in lineage.items():
        task = task_map.get(task_id)
        if not task:
            continue

        task_label = f"[cyan]{task.task_type}[/cyan]"
        if task.model:
            task_label += f" [dim]({task.model})[/dim]"

        task_branch = tree.add(task_label)

        # Add sources as leaves
        for source in sources:
            # Truncate long source names
            display_source = source if len(source) <= 60 else source[:57] + "..."

            # Color code by source type
            if source.startswith("http"):
                source_style = "blue"
            elif source.endswith((".pdf", ".doc", ".docx", ".txt")):
                source_style = "green"
            elif source.startswith("report:") or source.startswith("finding:"):
                source_style = "yellow"
            else:
                source_style = "white"

            task_branch.add(f"[{source_style}]← {display_source}[/{source_style}]")

    console.print(tree)

    # Summary stats
    total_sources = sum(len(s) for s in lineage.values())
    unique_sources = len(set(s for sources in lineage.values() for s in sources))

    console.print(
        f"\n[dim]Tasks with context: {len(lineage)} | Total references: {total_sources} | Unique sources: {unique_sources}[/dim]"
    )
