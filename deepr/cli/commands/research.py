"""Research commands - submit and manage individual research jobs."""

import click
from typing import Optional
from deepr.branding import print_section_header, CHECK, CROSS
# # from deepr.services.cost_estimation import CostEstimator


@click.group()
def research():
    """Submit and manage research jobs."""
    pass


@research.command()
@click.argument("prompt")
@click.option("--model", "-m", default="o4-mini-deep-research",
              type=click.Choice(["o4-mini-deep-research", "o3-deep-research"]),
              help="Deep research model (o4-mini faster/cheaper, o3 more comprehensive)")
@click.option("--priority", "-p", default=3, type=click.IntRange(1, 5),
              help="Priority (1=high, 5=low)")
@click.option("--web-search/--no-web-search", default=True,
              help="Enable web search (default: enabled, required for deep research)")
@click.option("--yes", "-y", is_flag=True,
              help="Skip confirmation prompt")
def submit(prompt: str, model: str, priority: int, web_search: bool, yes: bool):
    """
    Submit a deep research job.

    Note: Deep research jobs use agentic models that conduct multi-step research.
    They can take tens of minutes and cost more than regular API calls.

    Example:
        deepr research submit "What are the latest trends in AI?"
        deepr research submit "Market analysis: electric vehicles" --model o3-deep-research
    """
    print_section_header("Submit Deep Research Job")

    click.echo(f"\nConfiguration:")
    click.echo(f"   Model: {model}")
    click.echo(f"   Priority: {priority} ({'high' if priority <= 2 else 'normal' if priority <= 4 else 'low'})")
    click.echo(f"   Web Search: {'enabled' if web_search else 'disabled'}")
    click.echo(f"   Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}")

    click.echo(f"\nNote: Deep research jobs typically take 2-10 minutes for simple queries,")
    click.echo(f"      and can take 30+ minutes for comprehensive reports.")

    # Confirmation
    if not yes:
        if not click.confirm(f"\nSubmit deep research job?"):
            click.echo(f"\n{CROSS} Cancelled")
            return

    # Submit job
    click.echo(f"\n{CHECK} Submitting job...")

    try:
        import asyncio
        import uuid
        from datetime import datetime
        from deepr.queue import create_queue
        from deepr.queue.base import ResearchJob, JobStatus
        from deepr.providers import create_provider
        from deepr.providers.base import ResearchRequest, ToolConfig
        from deepr.config import load_config

        # Load config
        config = load_config()

        # Create queue and provider
        queue = create_queue("local", db_path=config.get("queue_db_path", "queue/research_queue.db"))
        provider = create_provider(
            config.get("provider", "openai"),
            api_key=config.get("api_key")
        )

        # Create job
        job_id = str(uuid.uuid4())
        job = ResearchJob(
            id=job_id,
            prompt=prompt,
            model=model,
            status=JobStatus.QUEUED,
            priority=priority,
            submitted_at=datetime.utcnow(),
            cost_limit=config.get("max_cost_per_job", 10.0),
            enable_web_search=web_search,
        )

        # Enqueue
        async def submit_job():
            await queue.enqueue(job)

            # Submit to provider
            request = ResearchRequest(
                prompt=prompt,
                model=model,
                system_message="You are a helpful AI research assistant. Provide comprehensive, well-researched responses with inline citations.",
                tools=[ToolConfig(type="web_search_preview")] if web_search else [],
                background=True,
            )

            provider_job_id = await provider.submit_research(request)

            # Update job with provider ID
            await queue.update_status(
                job_id=job_id,
                status=JobStatus.PROCESSING,
                provider_job_id=provider_job_id
            )

            return provider_job_id

        provider_job_id = asyncio.run(submit_job())

        click.echo(f"\n{CHECK} Job submitted successfully!")
        click.echo(f"\nJob ID: {job_id}")
        click.echo(f"Provider Job ID: {provider_job_id}")
        click.echo(f"\nNext steps:")
        click.echo(f"   deepr research wait {job_id[:8]}  (recommended - waits and shows result)")
        click.echo(f"   deepr research status {job_id[:8]}")
        click.echo(f"\nNote: Research agent will auto-update status when job completes.")
        click.echo(f"      Typical completion time: 2-10 minutes (simple) to 30+ minutes (comprehensive)")

    except Exception as e:
        click.echo(f"\n{CROSS} Error: {e}", err=True)
        raise click.Abort()


@research.command()
@click.argument("job_id")
def status(job_id: str):
    """
    Check status of a research job.

    Example:
        deepr research status abc123
    """
    print_section_header(f"Job Status: {job_id[:8]}...")

    try:
        import asyncio
        from deepr.queue import create_queue
        from deepr.config import load_config

        config = load_config()
        queue = create_queue("local", db_path=config.get("queue_db_path", "queue/research_queue.db"))

        async def get_status():
            return await queue.get_job(job_id)

        job = asyncio.run(get_status())

        if not job:
            click.echo(f"\n{CROSS} Job not found: {job_id}", err=True)
            raise click.Abort()

        click.echo(f"\nStatus: {job.status.value.upper()}")
        click.echo(f"\nDetails:")
        click.echo(f"   ID: {job.id}")
        click.echo(f"   Model: {job.model}")
        click.echo(f"   Priority: {job.priority}")
        click.echo(f"   Submitted: {job.submitted_at}")
        if job.started_at:
            click.echo(f"   Started: {job.started_at}")
        if job.completed_at:
            click.echo(f"   Completed: {job.completed_at}")

        if job.cost:
            click.echo(f"   Cost: ${job.cost:.4f}")
        if job.tokens_used:
            click.echo(f"   Tokens: {job.tokens_used:,}")

        click.echo(f"\nPrompt:")
        click.echo(f"   {job.prompt}")

        if job.status.value == "completed":
            click.echo(f"\nView result: deepr research result {job.id[:8]}")
        elif job.status.value == "processing":
            click.echo(f"\nJob is still processing... (usually takes 2-5 minutes)")
        elif job.status.value == "failed" and job.last_error:
            click.echo(f"\nError: {job.last_error}")

    except Exception as e:
        click.echo(f"\n{CROSS} Error: {e}", err=True)
        raise click.Abort()


@research.command()
@click.argument("job_id")
def result(job_id: str):
    """
    View result of a completed research job.

    Example:
        deepr research result abc123
    """
    print_section_header(f"Research Result: {job_id[:8]}...")

    try:
        import asyncio
        from deepr.queue import create_queue
        from deepr.providers import create_provider
        from deepr.config import load_config

        config = load_config()
        queue = create_queue("local", db_path=config.get("queue_db_path", "queue/research_queue.db"))
        provider = create_provider(config.get("provider", "openai"), api_key=config.get("api_key"))

        async def get_result():
            # Get job from queue
            job = await queue.get_job(job_id)
            if not job:
                return None, None

            if job.status.value != "completed":
                return job, None

            # Get result from provider
            if job.provider_job_id:
                response = await provider.get_status(job.provider_job_id)
                return job, response

            return job, None

        job, response = asyncio.run(get_result())

        if not job:
            click.echo(f"\n{CROSS} Job not found: {job_id}", err=True)
            raise click.Abort()

        if not response or job.status.value != "completed":
            click.echo(f"\n{CROSS} Result not available yet", err=True)
            click.echo(f"Status: {job.status.value.upper()}")
            click.echo(f"\nCheck status: deepr research status {job_id[:8]}")
            raise click.Abort()

        click.echo(f"\n{CHECK} Research Report:\n")

        # Print the message content
        if response.output:
            for block in response.output:
                if block.get('type') == 'message':
                    for content in block.get('content', []):
                        text = content.get('text', '')
                        if text:
                            click.echo(text)

                        # Print citations
                        annotations = content.get('annotations', [])
                        if annotations:
                            click.echo(f"\n\nCitations ({len(annotations)}):")
                            for i, ann in enumerate(annotations, 1):
                                click.echo(f"   [{i}] {ann.get('title', 'Untitled')}")
                                if ann.get('url'):
                                    click.echo(f"       {ann['url']}")

        # Print usage stats
        if response.usage:
            click.echo(f"\n\nUsage:")
            click.echo(f"   Input tokens: {response.usage.input_tokens:,}")
            click.echo(f"   Output tokens: {response.usage.output_tokens:,}")
            click.echo(f"   Total tokens: {response.usage.total_tokens:,}")
            click.echo(f"   Cost: ${response.usage.cost:.4f}")

    except Exception as e:
        click.echo(f"\n{CROSS} Error: {e}", err=True)
        raise click.Abort()


@research.command()
@click.argument("job_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def cancel(job_id: str, yes: bool):
    """
    Cancel a research job.

    This will cancel the job at the provider (OpenAI) and mark it as failed in the queue.

    Example:
        deepr research cancel abc123
        deepr research cancel abc123 --yes
    """
    print_section_header(f"Cancel Job: {job_id[:8]}...")

    try:
        import asyncio
        from deepr.queue import create_queue
        from deepr.queue.base import JobStatus
        from deepr.providers import create_provider
        from deepr.config import load_config

        config = load_config()
        queue = create_queue("local", db_path=config.get("queue_db_path", "queue/research_queue.db"))
        provider = create_provider(config.get("provider", "openai"), api_key=config.get("api_key"))

        async def cancel_job():
            # Get job
            job = await queue.get_job(job_id)
            if not job:
                return None, "Job not found"

            # Check if already completed/failed
            if job.status.value == "completed":
                return job, "Job already completed"
            if job.status.value == "failed":
                return job, "Job already failed"

            return job, None

        job, error = asyncio.run(cancel_job())

        if error:
            click.echo(f"\n{CROSS} {error}", err=True)
            raise click.Abort()

        if not job:
            click.echo(f"\n{CROSS} Job not found: {job_id}", err=True)
            raise click.Abort()

        # Show job details
        click.echo(f"\nJob Details:")
        click.echo(f"   ID: {job.id}")
        click.echo(f"   Status: {job.status.value.upper()}")
        click.echo(f"   Prompt: {job.prompt[:80]}{'...' if len(job.prompt) > 80 else ''}")
        if job.provider_job_id:
            click.echo(f"   Provider Job ID: {job.provider_job_id}")

        # Confirmation
        if not yes:
            if not click.confirm(f"\nCancel this job?"):
                click.echo(f"\n{CROSS} Cancelled")
                return

        click.echo(f"\n{CHECK} Cancelling job...")

        async def do_cancel():
            # Cancel at provider if we have a provider job ID
            if job.provider_job_id:
                try:
                    await provider.cancel_job(job.provider_job_id)
                    click.echo(f"{CHECK} Cancelled at provider")
                except Exception as e:
                    click.echo(f"   Warning: Could not cancel at provider: {e}")

            # Update queue status to failed
            await queue.update_status(
                job_id=job.id,
                status=JobStatus.FAILED,
                error="Cancelled by user"
            )

        asyncio.run(do_cancel())

        click.echo(f"\n{CHECK} Job cancelled successfully!")

    except Exception as e:
        click.echo(f"\n{CROSS} Error: {e}", err=True)
        raise click.Abort()


@research.command()
@click.argument("job_id")
@click.option("--timeout", "-t", default=300, help="Timeout in seconds (default: 300)")
def wait(job_id: str, timeout: int):
    """
    Wait for a job to complete and show result.

    Example:
        deepr research wait abc123
        deepr research wait abc123 --timeout 600
    """
    import asyncio
    import time
    from deepr.queue import create_queue
    from deepr.providers import create_provider
    from deepr.config import load_config

    print_section_header(f"Waiting for Job: {job_id[:8]}...")

    try:
        config = load_config()
        queue = create_queue("local", db_path=config.get("queue_db_path", "queue/research_queue.db"))
        provider = create_provider(config.get("provider", "openai"), api_key=config.get("api_key"))

        start_time = time.time()
        check_interval = 10  # Check every 10 seconds

        async def wait_for_completion():
            while True:
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    return None, "Timeout"

                # Check queue status
                job = await queue.get_job(job_id)
                if not job:
                    return None, "Job not found"

                if job.status.value == "completed":
                    # Get result
                    if job.provider_job_id:
                        response = await provider.get_status(job.provider_job_id)
                        return job, response
                    return job, None

                elif job.status.value == "failed":
                    return job, "Job failed"

                # Still processing
                click.echo(f"  [{int(elapsed)}s] Status: {job.status.value.upper()}...")
                await asyncio.sleep(check_interval)

        job, response = asyncio.run(wait_for_completion())

        if not job:
            click.echo(f"\n{CROSS} {response}", err=True)
            raise click.Abort()

        if response == "Job failed":
            click.echo(f"\n{CROSS} Job failed")
            if job.last_error:
                click.echo(f"Error: {job.last_error}")
            raise click.Abort()

        if not response:
            click.echo(f"\n{CROSS} Result not available", err=True)
            raise click.Abort()

        # Display result
        click.echo(f"\n{CHECK} Job completed!\n")

        # Print the message content
        if response.output:
            for block in response.output:
                if block.get('type') == 'message':
                    for content in block.get('content', []):
                        text = content.get('text', '')
                        if text:
                            click.echo(text)

        # Print usage
        if response.usage:
            click.echo(f"\n\nCost: ${response.usage.cost:.4f} | Tokens: {response.usage.total_tokens:,}")

    except Exception as e:
        click.echo(f"\n{CROSS} Error: {e}", err=True)
        raise click.Abort()
