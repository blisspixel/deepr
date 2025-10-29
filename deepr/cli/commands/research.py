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
@click.option("--files", "-f", multiple=True, type=click.Path(exists=True),
              help="Upload files for context (PDF, DOCX, TXT, MD, code files)")
@click.option("--vector-store", "-v", default=None,
              help="Use existing vector store by ID or name (created with 'deepr vector create')")
@click.option("--refine-prompt", is_flag=True,
              help="Automatically refine prompt to follow best practices (adds date context, structure)")
@click.option("--dry-run", is_flag=True,
              help="Show what would be done without actually submitting (useful with --refine-prompt)")
@click.option("--web-search/--no-web-search", default=True,
              help="Enable web search (default: enabled, required for deep research)")
@click.option("--yes", "-y", is_flag=True,
              help="Skip confirmation prompt")
def submit(prompt: str, model: str, priority: int, files: tuple, vector_store: Optional[str], refine_prompt: bool, dry_run: bool, web_search: bool, yes: bool):
    """
    Submit a deep research job.

    Note: Deep research jobs use agentic models that conduct multi-step research.
    They can take tens of minutes and cost more than regular API calls.

    Example:
        deepr research submit "What are the latest trends in AI?"
        deepr research submit "Market analysis: electric vehicles" --model o3-deep-research
    """
    print_section_header("Submit Deep Research Job")

    # Check if auto-refine is enabled in config
    import os
    auto_refine = os.getenv("DEEPR_AUTO_REFINE", "false").lower() in ("true", "1", "yes")

    # Refine prompt if requested OR if auto-refine is enabled
    original_prompt = prompt
    if refine_prompt or auto_refine:
        try:
            from deepr.services.prompt_refiner import PromptRefiner
            if auto_refine and not refine_prompt:
                click.echo(f"\n{CHECK} Auto-refining prompt (DEEPR_AUTO_REFINE=true)...")
            else:
                click.echo(f"\n{CHECK} Refining prompt...")
            refiner = PromptRefiner()
            refinement = refiner.refine(prompt, has_files=bool(files))

            prompt = refinement["refined_prompt"]

            # Show what changed
            if refinement["changes_made"] and refinement["changes_made"][0] != "No refinement needed - prompt already follows best practices":
                click.echo(f"\n   Improvements made:")
                for change in refinement["changes_made"]:
                    # Handle Unicode issues on Windows
                    try:
                        click.echo(f"   - {change}")
                    except UnicodeEncodeError:
                        # Fallback: ASCII-safe version
                        click.echo(f"   - {change.encode('ascii', 'replace').decode('ascii')}")

                if refinement.get("needs_context"):
                    try:
                        click.echo(f"\n   Note: {refinement.get('context_suggestion', 'Consider adding more context')}")
                    except UnicodeEncodeError:
                        pass

                click.echo(f"\n   Original: {original_prompt[:80]}...")
                click.echo(f"   Refined:  {prompt[:80]}...")
            else:
                click.echo(f"   Prompt already follows best practices - no changes needed")

        except Exception as e:
            click.echo(f"\n   Warning: Could not refine prompt: {e}")
            click.echo(f"   Continuing with original prompt...")
            prompt = original_prompt

    # If dry-run, show configuration and exit
    if dry_run:
        click.echo(f"\n{CHECK} Dry-run mode - showing what would be submitted:\n")
        click.echo(f"Configuration:")
        click.echo(f"   Model: {model}")
        click.echo(f"   Priority: {priority} ({'high' if priority <= 2 else 'normal' if priority <= 4 else 'low'})")
        click.echo(f"   Web Search: {'enabled' if web_search else 'disabled'}")
        if files:
            click.echo(f"   Files: {len(files)} file(s)")
            for f in files:
                import os
                click.echo(f"      - {os.path.basename(f)}")

        click.echo(f"\nFinal Prompt:")
        click.echo(f"   {prompt}")

        # Estimate cost
        avg_cost = 0.50 if "mini" in model else 5.0
        click.echo(f"\nEstimated cost: ~${avg_cost:.2f}")
        click.echo(f"Estimated time: 5-15 minutes")
        click.echo(f"\nTo actually submit this research, remove the --dry-run flag")
        return

    click.echo(f"\nConfiguration:")
    click.echo(f"   Model: {model}")
    click.echo(f"   Priority: {priority} ({'high' if priority <= 2 else 'normal' if priority <= 4 else 'low'})")
    click.echo(f"   Web Search: {'enabled' if web_search else 'disabled'}")
    if files:
        click.echo(f"   Files: {len(files)} file(s)")
        for f in files:
            import os
            click.echo(f"      - {os.path.basename(f)}")
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

            # Handle file uploads or vector store
            vector_store_id = None

            # Check for existing vector store
            if vector_store:
                click.echo(f"\n{CHECK} Using existing vector store: {vector_store}")

                # Look up vector store by ID or name
                stores = await provider.list_vector_stores(limit=100)
                found = False
                for vs in stores:
                    if vs.id == vector_store or vs.name == vector_store:
                        vector_store_id = vs.id
                        found = True
                        click.echo(f"   {CHECK} Found vector store: {vs.name} ({vs.id[:8]}...)")
                        click.echo(f"   Files: {len(vs.file_ids)}")
                        break

                if not found:
                    click.echo(f"\n{CROSS} Vector store not found: {vector_store}", err=True)
                    click.echo(f"Available vector stores:")
                    for vs in stores[:5]:
                        click.echo(f"  - {vs.name} ({vs.id})")
                    raise Exception(f"Vector store not found: {vector_store}")

            # Otherwise handle file uploads
            elif files:
                click.echo(f"\n{CHECK} Uploading {len(files)} file(s)...")

                # Upload files
                file_ids = []
                for file_path in files:
                    import os
                    click.echo(f"   Uploading {os.path.basename(file_path)}...")
                    file_id = await provider.upload_document(file_path, purpose="assistants")
                    file_ids.append(file_id)
                    click.echo(f"   {CHECK} Uploaded (ID: {file_id[:8]}...)")

                # Create vector store
                import time
                vs_name = f"research-{job_id[:8]}-{int(time.time())}"
                click.echo(f"\n{CHECK} Creating vector store '{vs_name}'...")
                vs_obj = await provider.create_vector_store(vs_name, file_ids)
                vector_store_id = vs_obj.id
                click.echo(f"   {CHECK} Vector store created (ID: {vector_store_id[:8]}...)")

                # Wait for vector store to be ready
                click.echo(f"   Waiting for file indexing...")
                await provider.wait_for_vector_store(vector_store_id, timeout=300)
                click.echo(f"   {CHECK} Files indexed and ready!")

            # Build tools list
            tools = []
            if web_search:
                tools.append(ToolConfig(type="web_search_preview"))
            if vector_store_id:
                tools.append(ToolConfig(type="file_search", vector_store_ids=[vector_store_id]))

            # Submit to provider
            request = ResearchRequest(
                prompt=prompt,
                model=model,
                system_message="You are a helpful AI research assistant. Provide comprehensive, well-researched responses with inline citations.",
                tools=tools,
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
@click.option("--cost", is_flag=True, help="Show detailed cost breakdown")
def result(job_id: str, cost: bool):
    """
    View result of a completed research job.

    Example:
        deepr research result abc123
        deepr research result abc123 --cost    # Detailed cost breakdown
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

        # If --cost flag, show detailed breakdown
        if cost:
            click.echo(f"\n{CHECK} Cost Breakdown:\n")
            click.echo(f"Job Details:")
            click.echo(f"   ID: {job.id}")
            click.echo(f"   Model: {job.model}")
            click.echo(f"   Submitted: {job.submitted_at}")
            click.echo(f"   Completed: {job.completed_at}")

            if response.usage:
                click.echo(f"\nToken Usage:")
                click.echo(f"   Input tokens:  {response.usage.input_tokens:,}")
                click.echo(f"   Output tokens: {response.usage.output_tokens:,}")
                if response.usage.reasoning_tokens:
                    click.echo(f"   Reasoning tokens: {response.usage.reasoning_tokens:,}")
                click.echo(f"   Total tokens:  {response.usage.total_tokens:,}")

                click.echo(f"\nCost Calculation:")
                # Calculate input and output costs separately
                from deepr.providers.base import UsageStats
                input_cost = UsageStats.calculate_cost(response.usage.input_tokens, 0, response.model or job.model)
                output_cost = UsageStats.calculate_cost(0, response.usage.output_tokens, response.model or job.model)

                click.echo(f"   Input cost:  ${input_cost:.4f} ({response.usage.input_tokens:,} tokens)")
                click.echo(f"   Output cost: ${output_cost:.4f} ({response.usage.output_tokens:,} tokens)")
                click.echo(f"   Total cost:  ${response.usage.cost:.4f}")

                # Show pricing info
                click.echo(f"\nPricing (per 1M tokens):")
                if "o3-deep-research" in (response.model or job.model):
                    click.echo(f"   Model: o3-deep-research")
                    click.echo(f"   Input:  $11.00/M tokens")
                    click.echo(f"   Output: $44.00/M tokens")
                elif "o4-mini" in (response.model or job.model):
                    click.echo(f"   Model: o4-mini-deep-research")
                    click.echo(f"   Input:  $1.10/M tokens")
                    click.echo(f"   Output: $4.40/M tokens")

            click.echo(f"\nPrompt:")
            click.echo(f"   {job.prompt[:200]}{'...' if len(job.prompt) > 200 else ''}")
            return

        # Normal result display
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
            click.echo(f"\nTip: Use 'deepr research result {job_id[:8]} --cost' for detailed breakdown")

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
@click.argument("job_id", required=False)
@click.option("--all", is_flag=True, help="Download all completed jobs from provider")
def get(job_id: Optional[str], all: bool):
    """
    Get research results - checks provider and downloads if ready.

    Unlike 'wait', this checks once and returns immediately.
    Perfect for checking on jobs without running a continuous worker.

    Example:
        deepr research get abc123          # Get specific job
        deepr research get --all           # Download all completed jobs
    """
    import asyncio
    from deepr.queue import create_queue
    from deepr.providers import create_provider
    from deepr.config import load_config
    from deepr.queue.base import JobStatus

    # Validate arguments
    if all and job_id:
        click.echo(f"\n{CROSS} Cannot specify both job_id and --all", err=True)
        raise click.Abort()

    if not all and not job_id:
        click.echo(f"\n{CROSS} Must specify either job_id or --all", err=True)
        raise click.Abort()

    if all:
        print_section_header("Download All Completed Jobs")
    else:
        print_section_header(f"Getting Research: {job_id[:8]}...")

    try:
        config = load_config()
        queue = create_queue("local", db_path=config.get("queue_db_path", "queue/research_queue.db"))
        provider = create_provider(config.get("provider", "openai"), api_key=config.get("api_key"))

        if all:
            # Get all jobs with provider_job_id that are not completed
            async def download_all():
                jobs = await queue.list_jobs()

                # Filter to jobs that have provider IDs but aren't completed
                pending_jobs = [j for j in jobs if j.provider_job_id and j.status != JobStatus.COMPLETED]

                if not pending_jobs:
                    click.echo(f"\nNo pending jobs to check")
                    return []

                click.echo(f"\nFound {len(pending_jobs)} pending job(s) to check\n")

                results = []
                for job in pending_jobs:
                    click.echo(f"Checking job {job.id[:8]}...")

                    try:
                        # Check status at provider
                        response = await provider.get_status(job.provider_job_id)

                        if response.status == "completed":
                            click.echo(f"   {CHECK} Completed! Downloading...")

                            # Extract content
                            from deepr.storage import create_storage

                            content = ""
                            if response.output:
                                for block in response.output:
                                    if block.get('type') == 'message':
                                        for item in block.get('content', []):
                                            text = item.get('text', '')
                                            if text:
                                                content += text + "\n"

                            # Save to storage
                            storage = create_storage(
                                config.get("storage", "local"),
                                base_path=config.get("results_dir", "data/reports")
                            )

                            await storage.save_report(
                                job_id=job.id,
                                filename="report.md",
                                content=content.encode('utf-8'),
                                content_type="text/markdown"
                            )

                            # Update queue
                            cost = response.usage.cost if response.usage else 0
                            tokens = response.usage.total_tokens if response.usage else 0

                            await queue.update_results(
                                job_id=job.id,
                                report_paths={"markdown": "report.md"},
                                cost=cost,
                                tokens_used=tokens
                            )

                            await queue.update_status(job.id, JobStatus.COMPLETED)

                            click.echo(f"   Saved! Cost: ${cost:.4f}")
                            results.append((job, response))
                        else:
                            click.echo(f"   Still {response.status}...")

                    except Exception as e:
                        click.echo(f"   {CROSS} Error: {e}")

                    click.echo()

                return results

            results = asyncio.run(download_all())

            if results:
                click.echo(f"\n{CHECK} Downloaded {len(results)} completed job(s)")
            else:
                click.echo(f"\nNo new completions found")

            return

        async def check_and_download():
            # Get job from queue
            job = await queue.get_job(job_id)
            if not job:
                return None, "Job not found"

            if not job.provider_job_id:
                return job, "No provider job ID - job may not have been submitted"

            click.echo(f"\nLocal status: {job.status.value.upper()}")
            click.echo(f"Checking with provider...")

            # Check status at provider
            response = await provider.get_status(job.provider_job_id)

            click.echo(f"Provider status: {response.status.upper()}")

            # Update local queue if status changed
            if response.status == "completed" and job.status != JobStatus.COMPLETED:
                click.echo(f"\n{CHECK} Job completed! Downloading results...")

                # Extract content
                from deepr.storage import create_storage
                from deepr.config import load_config

                content = ""
                if response.output:
                    for block in response.output:
                        if block.get('type') == 'message':
                            for item in block.get('content', []):
                                text = item.get('text', '')
                                if text:
                                    content += text + "\n"

                # Save to storage
                config2 = load_config()
                storage = create_storage(
                    config2.get("storage", "local"),
                    base_path=config2.get("results_dir", "data/reports")
                )

                await storage.save_report(
                    job_id=job.id,
                    filename="report.md",
                    content=content.encode('utf-8'),
                    content_type="text/markdown"
                )

                # Update queue with cost/tokens
                cost = response.usage.cost if response.usage else 0
                tokens = response.usage.total_tokens if response.usage else 0

                await queue.update_results(
                    job_id=job.id,
                    report_paths={"markdown": "report.md"},
                    cost=cost,
                    tokens_used=tokens
                )

                # Mark as completed
                await queue.update_status(job.id, JobStatus.COMPLETED)

                click.echo(f"   Results saved! Cost: ${cost:.4f}")

                return job, response

            elif response.status == "failed":
                click.echo(f"\n{CROSS} Job failed at provider")
                await queue.update_status(
                    job_id=job.id,
                    status=JobStatus.FAILED,
                    error=response.error or "Unknown error"
                )
                return job, None

            else:
                click.echo(f"\nJob still {response.status}... check again later")
                return job, None

        job, response = asyncio.run(check_and_download())

        if not job:
            click.echo(f"\n{CROSS} {response}", err=True)
            raise click.Abort()

        if response and hasattr(response, 'output'):
            # Display result
            click.echo(f"\n{CHECK} Result downloaded!\n")

            if response.output:
                for block in response.output:
                    if block.get('type') == 'message':
                        for content in block.get('content', []):
                            text = content.get('text', '')
                            if text:
                                click.echo(text)

            if response.usage:
                click.echo(f"\n\nCost: ${response.usage.cost:.4f} | Tokens: {response.usage.total_tokens:,}")

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


@research.command()
@click.argument("job_id")
@click.option("--format", "-f",
              type=click.Choice(["markdown", "txt", "json", "html"]),
              default="markdown",
              help="Export format")
@click.option("--output", "-o", help="Output file path")
def export(job_id: str, format: str, output: Optional[str]):
    """
    Export research results in different formats.

    Example:
        deepr research export abc123 --format json
        deepr research export abc123 --format html --output report.html
    """
    print_section_header(f"Export Research: {job_id[:8]}...")

    try:
        import asyncio
        import json
        from pathlib import Path
        from deepr.queue import create_queue
        from deepr.providers import create_provider
        from deepr.config import load_config
        from deepr.queue.base import JobStatus

        config = load_config()
        queue = create_queue("local", db_path=config.get("queue_db_path", "queue/research_queue.db"))
        provider = create_provider(config.get("provider", "openai"), api_key=config.get("api_key"))

        async def get_research():
            job = await queue.get_job(job_id)
            if not job:
                return None, "Job not found"

            if job.status != JobStatus.COMPLETED:
                return None, f"Job not completed (status: {job.status.value})"

            if not job.provider_job_id:
                return None, "No provider job ID"

            response = await provider.get_status(job.provider_job_id)
            return job, response

        job, response = asyncio.run(get_research())

        if not job:
            click.echo(f"\n{CROSS} {response}", err=True)
            raise click.Abort()

        if not isinstance(response, str) and response.output:
            # Extract content
            content = ""
            for block in response.output:
                if block.get('type') == 'message':
                    for item in block.get('content', []):
                        text = item.get('text', '')
                        if text:
                            content += text + "\n"

            # Output path
            if not output:
                Path("reports").mkdir(exist_ok=True)
                ext = format if format != "txt" else "txt"
                output = f"reports/{job_id[:8]}.{ext}"

            # Format content
            if format == "json":
                output_content = json.dumps({
                    "job_id": job.id,
                    "model": job.model,
                    "prompt": job.prompt,
                    "content": content,
                    "cost": response.usage.cost if response.usage else 0
                }, indent=2)
            else:
                output_content = content

            # Write
            Path(output).parent.mkdir(parents=True, exist_ok=True)
            with open(output, 'w', encoding='utf-8') as f:
                f.write(output_content)

            click.echo(f"\n{CHECK} Exported to: {output}")

        else:
            click.echo(f"\n{CROSS} No content to export", err=True)
            raise click.Abort()

    except Exception as e:
        click.echo(f"\n{CROSS} Error: {e}", err=True)
        raise click.Abort()
