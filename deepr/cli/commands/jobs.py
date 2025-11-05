"""Job management commands - unified namespace for job operations."""

import click
import asyncio
from deepr.queue.local_queue import SQLiteQueue
from deepr.queue.base import JobStatus
from pathlib import Path
from deepr.cli.colors import (
    console, print_header, print_success, print_error,
    print_job_table, print_panel, print_markdown, print_status
)


@click.group()
def jobs():
    """Manage research jobs (list, status, get results, cancel)."""
    pass


@jobs.command()
@click.argument("job_id")
def status(job_id: str):
    """Show detailed status for a specific job.

    Examples:
        deepr jobs status abc123
        deepr jobs status research-1234567890
    """
    asyncio.run(_show_status(job_id))


async def _show_status(job_id: str):
    """Display job status."""
    from datetime import datetime, timezone

    queue = SQLiteQueue()
    job = await queue.get_job(job_id)

    if not job:
        click.echo(f"Job not found: {job_id}")
        return

    # Auto-check provider for long-running jobs
    if job.status == JobStatus.PROCESSING and job.provider_job_id:
        # Calculate elapsed time
        if job.submitted_at:
            if isinstance(job.submitted_at, str):
                submitted = datetime.fromisoformat(job.submitted_at.replace('Z', '+00:00'))
            else:
                submitted = job.submitted_at

            elapsed = datetime.now(timezone.utc) - submitted.replace(tzinfo=timezone.utc)
            elapsed_minutes = elapsed.total_seconds() / 60

            # Auto-check provider after 30 minutes
            if elapsed_minutes > 30:
                click.echo(f"\n[!] Job running {elapsed_minutes:.0f} minutes - checking provider API...")

                try:
                    from deepr.providers import create_provider
                    from deepr.config import load_config

                    config = load_config()
                    # Use the job's provider, not the config default
                    provider_name = job.provider if hasattr(job, 'provider') and job.provider else config.get("provider", "openai")

                    # Get provider-specific API key
                    if provider_name == "gemini":
                        api_key = config.get("gemini_api_key")
                    elif provider_name == "grok":
                        api_key = config.get("xai_api_key")
                    elif provider_name == "azure":
                        api_key = config.get("azure_api_key")
                    else:  # openai
                        api_key = config.get("api_key")

                    provider = create_provider(provider_name, api_key=api_key)
                    response = await provider.get_status(job.provider_job_id)

                    if response.status == "completed":
                        click.echo("[OK] Provider reports: COMPLETED (local DB was stale)")
                        click.echo("Use 'deepr jobs get " + job_id + "' to retrieve results\n")
                    elif response.status in ["failed", "expired", "cancelled"]:
                        click.echo(f"[X] Provider reports: {response.status.upper()} (local DB was stale)")
                        await queue.update_status(job_id, JobStatus.FAILED if response.status != "cancelled" else JobStatus.CANCELLED)
                        job = await queue.get_job(job_id)
                    else:
                        click.echo(f"[OK] Provider confirms: still {response.status}\n")
                except Exception as e:
                    click.echo(f"Warning: Could not verify with provider: {e}\n")

    click.echo("\n" + "="*70)
    click.echo("  Job Status")
    click.echo("="*70 + "\n")

    click.echo(f"ID: {job.id}")
    click.echo(f"Status: {job.status.value.upper()}")
    click.echo(f"Model: {job.model}")
    click.echo(f"\nPrompt: {job.prompt}")

    click.echo(f"\nSubmitted: {job.submitted_at.strftime('%Y-%m-%d %H:%M:%S')}")

    if job.started_at:
        click.echo(f"Started: {job.started_at.strftime('%Y-%m-%d %H:%M:%S')}")

    if job.completed_at:
        click.echo(f"Completed: {job.completed_at.strftime('%Y-%m-%d %H:%M:%S')}")
        duration = (job.completed_at - job.submitted_at).total_seconds()
        click.echo(f"Duration: {duration/60:.1f} minutes")

    if job.cost:
        click.echo(f"\nCost: ${job.cost:.4f}")

    if job.tokens_used:
        click.echo(f"Tokens: {job.tokens_used:,}")

    if job.last_error:
        click.echo(f"\nError: {job.last_error}")

    if job.report_paths:
        click.echo(f"\nReports:")
        for format_type, path in job.report_paths.items():
            click.echo(f"  {format_type}: {path}")

    click.echo()


@jobs.command()
@click.argument("job_id")
def get(job_id: str):
    """Get research results for a completed job.

    Examples:
        deepr jobs get abc123
        deepr jobs get research-1234567890
    """
    asyncio.run(_get_results(job_id))


async def _get_results(job_id: str):
    """Display job results - checks provider if not completed locally."""
    from datetime import datetime, timezone

    queue = SQLiteQueue()
    job = await queue.get_job(job_id)

    if not job:
        click.echo(f"Job not found: {job_id}")
        return

    # If not completed locally, try fetching from provider
    if job.status != JobStatus.COMPLETED and job.provider_job_id:
        click.echo(f"Job status: {job.status.value}")

        # Calculate elapsed time
        if job.submitted_at:
            if isinstance(job.submitted_at, str):
                submitted = datetime.fromisoformat(job.submitted_at.replace('Z', '+00:00'))
            else:
                submitted = job.submitted_at

            elapsed = datetime.now(timezone.utc) - submitted.replace(tzinfo=timezone.utc)
            elapsed_minutes = elapsed.total_seconds() / 60
            click.echo(f"Elapsed time: {elapsed_minutes:.1f} minutes")

            # Warn if job is taking unusually long
            if elapsed_minutes > 60:
                click.echo(f"[!] Warning: Job has been running for over an hour")
                click.echo(f"[!] This may indicate a stale status - checking provider...")

        click.echo(f"Checking provider for results...")

        try:
            from deepr.providers import create_provider
            from deepr.config import load_config
            from deepr.storage import create_storage

            config = load_config()
            # Use the job's provider, not the config default
            provider_name = job.provider if hasattr(job, 'provider') and job.provider else config.get("provider", "openai")

            # Get provider-specific API key
            if provider_name == "gemini":
                api_key = config.get("gemini_api_key")
            elif provider_name == "grok":
                api_key = config.get("xai_api_key")
            elif provider_name == "azure":
                api_key = config.get("azure_api_key")
            else:  # openai
                api_key = config.get("api_key")

            provider = create_provider(provider_name, api_key=api_key)

            # Fetch from provider
            response = await provider.get_status(job.provider_job_id)

            if response.status == "completed":
                click.echo("[OK] Retrieved results from provider")

                # Extract content from response
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
                storage = create_storage("local")
                report_metadata = await storage.save_report(
                    job_id=job_id,
                    filename="report.md",
                    content=content.encode('utf-8'),
                    content_type="text/markdown"
                )
                report_paths = {"markdown": report_metadata.url}

                # Update job in queue
                await queue.update_status(job_id, JobStatus.COMPLETED)
                if response.usage and response.usage.cost:
                    await queue.update_results(
                        job_id,
                        report_paths=report_paths,
                        cost=response.usage.cost,
                        tokens_used=response.usage.total_tokens if response.usage.total_tokens else 0
                    )

                job = await queue.get_job(job_id)
            elif response.status == "failed":
                click.echo(f"[X] Job failed at provider: {response.error}")
                await queue.update_status(job_id, JobStatus.FAILED)
                return
            elif response.status in ["expired", "cancelled"]:
                click.echo(f"[X] Job {response.status} at provider")
                await queue.update_status(job_id, JobStatus.FAILED if response.status == "expired" else JobStatus.CANCELLED)
                return
            else:
                click.echo(f"[OK] Confirmed with provider: Job still {response.status}")
                click.echo(f"Use 'deepr jobs status {job_id}' to check progress")
                return

        except Exception as e:
            click.echo(f"Error fetching from provider: {e}")
            return

    # Display results
    if job.status == JobStatus.COMPLETED:
        click.echo("\n" + "="*70)
        click.echo("  Research Results")
        click.echo("="*70 + "\n")

        if job.report_paths and "markdown" in job.report_paths:
            md_path = Path(job.report_paths["markdown"])
            if md_path.exists():
                content = md_path.read_text(encoding="utf-8")
                click.echo(content)
            else:
                click.echo(f"Report file not found: {md_path}")
        else:
            click.echo("No markdown report available")

        if job.cost:
            click.echo(f"\nCost: ${job.cost:.4f}")
    else:
        click.echo(f"Job not completed yet. Status: {job.status.value}")
        click.echo(f"Use 'deepr jobs status {job_id}' to check progress")


@jobs.command(name="list")
@click.option("--status", "-s", type=click.Choice(["queued", "processing", "completed", "failed", "cancelled"]), help="Filter by status")
@click.option("--limit", "-n", type=int, default=20, help="Number of jobs to show (default: 20)")
def list_jobs(status: str, limit: int):
    """List research jobs.

    Examples:
        deepr jobs list
        deepr jobs list --status completed
        deepr jobs list --limit 50
    """
    asyncio.run(_list_jobs(status, limit))


async def _refresh_job_statuses(queue, jobs):
    """Refresh job statuses from provider API."""
    try:
        from deepr.providers import create_provider
        from deepr.config import load_config
        from deepr.storage import create_storage

        config = load_config()
        storage = create_storage("local")

        for job in jobs:
            try:
                # Use the job's provider, not the config default
                provider_name = job.provider if hasattr(job, 'provider') and job.provider else config.get("provider", "openai")

                # Get provider-specific API key
                if provider_name == "gemini":
                    api_key = config.get("gemini_api_key")
                elif provider_name == "grok":
                    api_key = config.get("xai_api_key")
                elif provider_name == "azure":
                    api_key = config.get("azure_api_key")
                else:  # openai
                    api_key = config.get("api_key")

                provider = create_provider(provider_name, api_key=api_key)
                response = await provider.get_status(job.provider_job_id)

                if response.status == "completed":
                    # Download results
                    content = ""
                    if response.output:
                        for block in response.output:
                            if block.get('type') == 'message':
                                for item in block.get('content', []):
                                    if item.get('type') in ['output_text', 'text']:
                                        text = item.get('text', '')
                                        if text:
                                            content += text + "\n"

                    # Save report
                    report_metadata = await storage.save_report(
                        job_id=job.id,
                        filename="report.md",
                        content=content.encode('utf-8'),
                        content_type="text/markdown",
                        metadata={
                            "prompt": job.prompt,
                            "model": job.model,
                            "status": "completed",
                            "provider_job_id": job.provider_job_id,
                        }
                    )

                    # Update queue
                    await queue.update_status(job.id, JobStatus.COMPLETED)
                    if response.usage and response.usage.cost:
                        await queue.update_results(
                            job.id,
                            report_paths={"markdown": report_metadata.url},
                            cost=response.usage.cost
                        )

                elif response.status == "failed":
                    error_msg = response.error.message if response.error else "Unknown error"
                    await queue.update_status(job.id, JobStatus.FAILED, error=error_msg)

                # If still queued/processing, leave it (no update needed)

            except Exception as e:
                # Silently skip jobs that fail to refresh
                pass

    except Exception as e:
        # If provider init fails, silently skip refresh
        pass


async def _list_jobs(status_filter: str, limit: int):
    """List jobs from queue with automatic status refresh for stale jobs."""
    from datetime import datetime, timedelta, timezone

    queue = SQLiteQueue()
    jobs = await queue.list_jobs(limit=limit)

    # Filter by status if specified
    if status_filter:
        target_status = JobStatus(status_filter)
        jobs = [j for j in jobs if j.status == target_status]

    # Refresh stale jobs (>30 minutes old and not completed/failed)
    stale_threshold = datetime.now(timezone.utc) - timedelta(minutes=30)
    stale_jobs = [
        job for job in jobs
        if job.status in [JobStatus.QUEUED, JobStatus.PROCESSING]
        and job.submitted_at < stale_threshold
        and job.provider_job_id  # Only if we have a provider job ID
    ]

    if stale_jobs:
        click.echo(click.style(f"\nRefreshing status for {len(stale_jobs)} stale job(s)...", fg="yellow"), nl=False)
        await _refresh_job_statuses(queue, stale_jobs)
        click.echo(click.style(" done", fg="green"))
        # Re-fetch jobs after refresh
        jobs = await queue.list_jobs(limit=limit)
        if status_filter:
            target_status = JobStatus(status_filter)
            jobs = [j for j in jobs if j.status == target_status]

    if not jobs:
        click.echo(click.style("\nNo jobs found\n", fg="yellow"))
        return

    # Group jobs by campaign/prefix
    from collections import defaultdict
    campaigns = defaultdict(list)
    standalone_jobs = []

    for job in jobs:
        # Extract campaign prefix (e.g., "team-abc123" -> "team")
        if '-' in job.id:
            parts = job.id.split('-', 1)
            prefix = parts[0]
            # Group if multiple jobs share the same prefix and submitted around same time
            campaign_key = f"{prefix}-{job.submitted_at.strftime('%Y%m%d%H%M')}" if job.submitted_at else prefix
            campaigns[campaign_key].append(job)
        else:
            standalone_jobs.append(job)

    # Determine which are actually campaigns (multiple jobs with same key)
    actual_campaigns = {k: v for k, v in campaigns.items() if len(v) > 1}
    for k, v in campaigns.items():
        if len(v) == 1:
            standalone_jobs.extend(v)

    # Print header with color
    click.echo()
    click.echo(click.style("Research Jobs", fg="cyan", bold=True))
    click.echo(click.style("-" * 13, dim=True))
    click.echo()

    # Print campaigns first (grouped)
    for campaign_key, campaign_jobs in sorted(actual_campaigns.items(), key=lambda x: x[1][0].submitted_at, reverse=True):
        campaign_type = campaign_key.split('-')[0]

        # Campaign header
        all_completed = all(j.status == JobStatus.COMPLETED for j in campaign_jobs)
        any_failed = any(j.status == JobStatus.FAILED for j in campaign_jobs)
        any_processing = any(j.status == JobStatus.PROCESSING for j in campaign_jobs)

        if all_completed:
            campaign_status = click.style("[OK]", fg="green", bold=True)
        elif any_failed:
            campaign_status = click.style("[X]", fg="red", bold=True)
        elif any_processing:
            campaign_status = click.style("[>>]", fg="cyan", bold=True)
        else:
            campaign_status = click.style("[ ]", dim=True)

        total_cost = sum(j.cost for j in campaign_jobs if j.cost)
        click.echo(click.style(f"▼ {campaign_type.upper()} Campaign", fg="yellow", bold=True) + f" ({len(campaign_jobs)} jobs)")

        # Show first job's details as campaign representative
        first_job = campaign_jobs[0]
        prompt = first_job.prompt[:60] + "..." if len(first_job.prompt) > 60 else first_job.prompt
        click.echo(f"  {campaign_status} {prompt}")

        if first_job.submitted_at:
            time_display = click.style(first_job.submitted_at.strftime('%Y-%m-%d %H:%M:%S'), dim=True)
            click.echo(f"  Submitted: {time_display}")

        if total_cost > 0:
            cost_display = click.style(f"${total_cost:.4f}", fg="yellow")
            click.echo(f"  Total Cost: {cost_display}")

        # Show individual jobs in campaign (indented)
        click.echo(click.style(f"  Jobs:", dim=True))
        for job in campaign_jobs:
            if job.status == JobStatus.COMPLETED:
                status_icon = click.style("[OK]", fg="green")
            elif job.status == JobStatus.PROCESSING:
                status_icon = click.style("[>>]", fg="cyan")
            elif job.status == JobStatus.FAILED:
                status_icon = click.style("[X]", fg="red")
            else:
                status_icon = click.style("[ ]", dim=True)

            job_id = click.style(job.id[:15], fg="cyan")
            cost_str = f" (${job.cost:.4f})" if job.cost else ""
            click.echo(f"    {status_icon} {job_id}{cost_str}")

        click.echo()

    # Print standalone jobs
    for job in sorted(standalone_jobs, key=lambda x: x.submitted_at, reverse=True):
        # Status with color
        if job.status == JobStatus.COMPLETED:
            status_display = click.style("[OK]", fg="green", bold=True)
        elif job.status == JobStatus.PROCESSING:
            status_display = click.style("[>>]", fg="cyan", bold=True)
        elif job.status == JobStatus.FAILED:
            status_display = click.style("[X]", fg="red", bold=True)
        else:
            status_display = click.style("[ ]", dim=True)

        # Format job info
        job_id = click.style(job.id[:12], fg="cyan")
        model = click.style(job.model, fg="blue")
        prompt = job.prompt[:50] + "..." if len(job.prompt) > 50 else job.prompt

        click.echo(f"{status_display} {job_id} | {model}")
        click.echo(f"  {prompt}")

        if job.cost:
            cost_display = click.style(f"${job.cost:.4f}", fg="yellow")
            click.echo(f"  Cost: {cost_display}")

        if job.submitted_at:
            time_display = click.style(job.submitted_at.strftime('%Y-%m-%d %H:%M:%S'), dim=True)
            click.echo(f"  Submitted: {time_display}")

        click.echo()


@jobs.command()
@click.argument("job_id")
def cancel(job_id: str):
    """Cancel a queued or processing job.

    Examples:
        deepr jobs cancel abc123
        deepr jobs cancel research-1234567890
    """
    asyncio.run(_cancel_job(job_id))


async def _cancel_job(job_id: str):
    """Cancel a job."""
    queue = SQLiteQueue()
    job = await queue.get_job(job_id)

    if not job:
        click.echo(f"Job not found: {job_id}")
        return

    if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
        click.echo(f"Job already {job.status.value}, cannot cancel")
        return

    # Try to cancel with provider if it's processing
    if job.provider_job_id and job.status == JobStatus.PROCESSING:
        try:
            from deepr.providers import create_provider
            from deepr.config import load_config

            config = load_config()
            provider = create_provider(config.get("provider", "openai"), api_key=config.get("api_key"))

            cancelled = await provider.cancel_job(job.provider_job_id)
            if cancelled:
                click.echo("[OK] Cancelled with provider")
        except Exception as e:
            click.echo(f"Warning: Could not cancel with provider: {e}")

    # Update local queue
    await queue.update_status(job_id, JobStatus.CANCELLED)
    click.echo(f"[OK] Job {job_id[:12]} cancelled")


if __name__ == "__main__":
    jobs()
