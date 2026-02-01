"""Job status and management commands."""

import click
import asyncio
import json
from typing import Optional
from deepr.queue.local_queue import SQLiteQueue
from deepr.queue.base import JobStatus
from pathlib import Path
from deepr.cli.colors import print_deprecation, console
from deepr.cli.output import OutputContext, OutputMode, OutputFormatter, output_options, format_duration, format_cost


@click.command()
@click.argument("job_id")
@output_options
def status(job_id: str, output_context: OutputContext):
    """[DEPRECATED: Use 'deepr jobs status'] Show detailed status for a specific job.

    Examples:
        deepr status abc123
        deepr status research-1234567890
    """
    if output_context.mode == OutputMode.VERBOSE:
        print_deprecation("deepr status <job-id>", "deepr jobs status <job-id>")
    asyncio.run(_show_status(job_id, output_context))


async def _show_status(job_id: str, output_context: Optional[OutputContext] = None):
    """Display job status.
    
    Args:
        job_id: Job identifier
        output_context: Output formatting context (optional for backward compatibility)
    """
    # Create default output context if not provided (backward compatibility)
    if output_context is None:
        output_context = OutputContext(mode=OutputMode.VERBOSE)
    
    queue = SQLiteQueue()
    job = await queue.get_job(job_id)

    if not job:
        if output_context.mode == OutputMode.JSON:
            print(json.dumps({"status": "error", "error": f"Job not found: {job_id}"}))
        elif output_context.mode != OutputMode.QUIET:
            click.echo(f"Job not found: {job_id}")
        return

    # JSON output mode
    if output_context.mode == OutputMode.JSON:
        job_data = {
            "id": job.id,
            "status": job.status.value,
            "model": job.model,
            "prompt": job.prompt,
            "submitted_at": job.submitted_at.isoformat() if job.submitted_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "cost": job.cost,
            "tokens_used": job.tokens_used,
            "error": job.last_error,
            "report_paths": job.report_paths or {}
        }
        print(json.dumps(job_data))
        return
    
    # Quiet mode - no output for status queries
    if output_context.mode == OutputMode.QUIET:
        return
    
    # Minimal mode - single line summary
    if output_context.mode == OutputMode.MINIMAL:
        status_str = job.status.value.upper()
        cost_str = f"${job.cost:.4f}" if job.cost else "$0.00"
        click.echo(f"{status_str} | {job.id[:12]} | {cost_str}")
        return

    # Verbose mode - full details
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
        click.echo(f"Duration: {format_duration(duration)}")

    if job.cost:
        click.echo(f"\nCost: {format_cost(job.cost)}")

    if job.tokens_used:
        click.echo(f"Tokens: {job.tokens_used:,}")

    if job.last_error:
        click.echo(f"\nError: {job.last_error}")

    if job.report_paths:
        click.echo(f"\nReports:")
        for format_type, path in job.report_paths.items():
            click.echo(f"  {format_type}: {path}")

    click.echo()


@click.command()
@click.argument("job_id")
@output_options
def get(job_id: str, output_context: OutputContext):
    """[DEPRECATED: Use 'deepr jobs get'] Get research results for a completed job.

    Examples:
        deepr get abc123
        deepr get research-1234567890
    """
    if output_context.mode == OutputMode.VERBOSE:
        print_deprecation("deepr get <job-id>", "deepr jobs get <job-id>")
    asyncio.run(_get_results(job_id, output_context))


async def _get_results(job_id: str, output_context: Optional[OutputContext] = None):
    """Display job results - checks provider if not completed locally.
    
    Args:
        job_id: Job identifier
        output_context: Output formatting context (optional for backward compatibility)
    """
    # Create default output context if not provided (backward compatibility)
    if output_context is None:
        output_context = OutputContext(mode=OutputMode.VERBOSE)
    
    queue = SQLiteQueue()
    job = await queue.get_job(job_id)

    if not job:
        if output_context.mode == OutputMode.JSON:
            print(json.dumps({"status": "error", "error": f"Job not found: {job_id}"}))
        elif output_context.mode != OutputMode.QUIET:
            click.echo(f"Job not found: {job_id}")
        return

    # If not completed locally, try fetching from provider
    if job.status != JobStatus.COMPLETED and job.provider_job_id:
        if output_context.mode == OutputMode.VERBOSE:
            click.echo(f"Job status: {job.status.value}")
            click.echo(f"Checking provider for results...")

        try:
            from deepr.providers import create_provider
            from deepr.config import load_config
            from deepr.storage import create_storage

            config = load_config()

            # Get provider-specific API key based on job's provider
            if job.provider == "gemini":
                api_key = config.get("gemini_api_key")
            elif job.provider in ["grok", "xai"]:
                api_key = config.get("xai_api_key")
            elif job.provider == "azure":
                api_key = config.get("azure_api_key")
            else:  # openai
                api_key = config.get("api_key")

            provider = create_provider(job.provider, api_key=api_key)

            # Check status at provider
            response = await provider.get_status(job.provider_job_id)

            if response.status == "completed":
                if output_context.mode == OutputMode.VERBOSE:
                    click.echo(f"Found completed results at provider! Downloading...")

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
                storage = create_storage(
                    config.get("storage", "local"),
                    base_path=config.get("results_dir", "data/reports")
                )

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

                # Update queue status
                await queue.update_status(job.id, JobStatus.COMPLETED)
                if response.usage and response.usage.cost:
                    await queue.update_results(
                        job.id,
                        report_paths={"markdown": report_metadata.url},
                        cost=response.usage.cost
                    )

                # Update job object
                job.status = JobStatus.COMPLETED
                job.report_paths = {"markdown": report_metadata.url}
                if response.usage:
                    job.cost = response.usage.cost

                if output_context.mode == OutputMode.VERBOSE:
                    click.echo(f"Results downloaded successfully!")

            elif response.status == "failed":
                error_msg = response.error.message if response.error else "Unknown error"
                if output_context.mode == OutputMode.JSON:
                    print(json.dumps({"status": "error", "error": f"Job failed at provider: {error_msg}"}))
                elif output_context.mode != OutputMode.QUIET:
                    click.echo(f"Job failed at provider: {error_msg}")
                await queue.update_status(job.id, JobStatus.FAILED, error=error_msg)
                return

            else:
                if output_context.mode == OutputMode.JSON:
                    print(json.dumps({"status": "pending", "provider_status": response.status, "job_id": job_id}))
                elif output_context.mode != OutputMode.QUIET:
                    click.echo(f"Job still {response.status} at provider.")
                    click.echo(f"Use 'deepr status {job_id[:12]}' to check again later.")
                return

        except Exception as e:
            if output_context.mode == OutputMode.JSON:
                print(json.dumps({"status": "error", "error": f"Error checking provider: {e}"}))
            elif output_context.mode != OutputMode.QUIET:
                click.echo(f"Error checking provider: {e}")
                click.echo(f"Job status locally: {job.status.value}")
            return

    elif job.status != JobStatus.COMPLETED:
        if output_context.mode == OutputMode.JSON:
            print(json.dumps({"status": "pending", "job_status": job.status.value, "job_id": job_id}))
        elif output_context.mode != OutputMode.QUIET:
            click.echo(f"Job not completed yet. Status: {job.status.value}")
            click.echo(f"Use 'deepr status {job_id[:12]}' to check progress.")
        return

    # Job is completed - output results based on mode
    report_path = None
    content = None
    content_size = 0
    
    if job.report_paths and "markdown" in job.report_paths:
        report_path = Path(job.report_paths["markdown"])
        if report_path.exists():
            content = report_path.read_text(encoding="utf-8")
            content_size = len(content)

    # JSON output mode
    if output_context.mode == OutputMode.JSON:
        result_data = {
            "status": "success",
            "job_id": job.id,
            "query": job.prompt,
            "model": job.model,
            "cost": job.cost or 0.0,
            "report_path": str(report_path) if report_path else None,
            "content_size": content_size
        }
        print(json.dumps(result_data))
        return
    
    # Quiet mode - no output
    if output_context.mode == OutputMode.QUIET:
        return
    
    # Minimal mode - single line summary
    if output_context.mode == OutputMode.MINIMAL:
        cost_str = f"${job.cost:.4f}" if job.cost else "$0.00"
        path_str = str(report_path) if report_path else "no report"
        click.echo(f"COMPLETED | {job.id[:12]} | {cost_str} | {path_str}")
        return

    # Verbose mode - full details
    click.echo("\n" + "="*70)
    click.echo("  Research Results")
    click.echo("="*70 + "\n")

    click.echo(f"Query: {job.prompt}")
    click.echo(f"Model: {job.model}")
    click.echo(f"Cost: {format_cost(job.cost) if job.cost else '$0.00'}")
    click.echo()

    if report_path and report_path.exists():
        click.echo(f"Report saved: {report_path}")
        click.echo(f"Size: {content_size:,} characters")
        click.echo()

        # Show preview for large reports
        if content_size > 5000:
            click.echo("="*70)
            click.echo("Report Preview (first 2000 characters):")
            click.echo("="*70)
            click.echo(content[:2000])
            click.echo()
            click.echo(f"... ({content_size - 2000:,} more characters)")
            click.echo()
            click.echo(f"Full report: {report_path}")
            click.echo("="*70)
        else:
            click.echo("="*70)
            click.echo(content)
            click.echo("="*70)
    elif report_path:
        click.echo(f"Report file not found: {report_path}")
    else:
        click.echo("No report available yet.")

    click.echo()


@click.command()
@click.option("--status-filter", "-s", help="Filter by status (queued/processing/completed/failed)")
@click.option("--limit", "-n", type=int, default=10, help="Number of jobs to show")
@output_options
def list_jobs(status_filter: str, limit: int, output_context: OutputContext):
    """[DEPRECATED: Use 'deepr jobs list'] List research jobs.

    Examples:
        deepr list
        deepr list -s processing
        deepr list -s completed -n 20
    """
    if output_context.mode == OutputMode.VERBOSE:
        print_deprecation("deepr list", "deepr jobs list")
    asyncio.run(_list_jobs(status_filter, limit, output_context))


async def _refresh_job_statuses(queue, jobs):
    """Refresh job statuses from provider API."""
    try:
        from deepr.providers import create_provider
        from deepr.config import load_config
        from deepr.storage import create_storage

        config = load_config()
        storage = create_storage(
            config.get("storage", "local"),
            base_path=config.get("results_dir", "data/reports")
        )

        for job in jobs:
            try:
                # Get provider-specific API key based on job's provider
                if job.provider == "gemini":
                    api_key = config.get("gemini_api_key")
                elif job.provider in ["grok", "xai"]:
                    api_key = config.get("xai_api_key")
                elif job.provider == "azure":
                    api_key = config.get("azure_api_key")
                else:  # openai
                    api_key = config.get("api_key")

                provider = create_provider(job.provider, api_key=api_key)
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


async def _list_jobs(status_filter: str, limit: int, output_context: Optional[OutputContext] = None):
    """List jobs with automatic status refresh for stale jobs.
    
    Args:
        status_filter: Filter by job status
        limit: Maximum number of jobs to return
        output_context: Output formatting context (optional for backward compatibility)
    """
    # Create default output context if not provided (backward compatibility)
    if output_context is None:
        output_context = OutputContext(mode=OutputMode.VERBOSE)
    
    queue = SQLiteQueue()

    # Parse status filter
    status_enum = None
    if status_filter:
        try:
            status_enum = JobStatus(status_filter.lower())
        except ValueError:
            if output_context.mode == OutputMode.JSON:
                print(json.dumps({"status": "error", "error": f"Invalid status: {status_filter}"}))
            elif output_context.mode != OutputMode.QUIET:
                click.echo(f"Invalid status: {status_filter}")
                click.echo("Valid statuses: queued, processing, completed, failed, cancelled")
            return

    jobs = await queue.list_jobs(status=status_enum, limit=limit)

    # Refresh stale jobs (>30 minutes old and not completed/failed) - only in verbose mode
    if output_context.mode == OutputMode.VERBOSE:
        from datetime import datetime, timedelta
        stale_threshold = datetime.utcnow() - timedelta(minutes=30)
        stale_jobs = [
            job for job in jobs
            if job.status in [JobStatus.QUEUED, JobStatus.PROCESSING]
            and job.submitted_at < stale_threshold
            and job.provider_job_id  # Only if we have a provider job ID
        ]

        if stale_jobs:
            click.echo(f"Refreshing status for {len(stale_jobs)} stale job(s)...", nl=False)
            await _refresh_job_statuses(queue, stale_jobs)
            click.echo(" done")
            # Re-fetch jobs after refresh
            jobs = await queue.list_jobs(status=status_enum, limit=limit)

    # JSON output mode
    if output_context.mode == OutputMode.JSON:
        jobs_data = []
        for job in jobs:
            jobs_data.append({
                "id": job.id,
                "status": job.status.value,
                "model": job.model,
                "prompt": job.prompt[:100] + "..." if len(job.prompt) > 100 else job.prompt,
                "submitted_at": job.submitted_at.isoformat() if job.submitted_at else None,
                "cost": job.cost,
                "error": job.last_error
            })
        print(json.dumps({"status": "success", "count": len(jobs), "jobs": jobs_data}))
        return
    
    # Quiet mode - no output
    if output_context.mode == OutputMode.QUIET:
        return

    if not jobs:
        if output_context.mode != OutputMode.QUIET:
            click.echo("No jobs found.")
        return

    # Minimal mode - compact list
    if output_context.mode == OutputMode.MINIMAL:
        for job in jobs:
            status_str = job.status.value.upper()
            cost_str = f"${job.cost:.4f}" if job.cost else "$0.00"
            prompt_preview = job.prompt[:40] + "..." if len(job.prompt) > 40 else job.prompt
            click.echo(f"{status_str:12} | {job.id[:12]} | {cost_str} | {prompt_preview}")
        return

    # Verbose mode - full details
    click.echo("\n" + "="*70)
    click.echo("  Job Queue")
    click.echo("="*70 + "\n")

    click.echo(f"Found {len(jobs)} job(s)\n")

    for job in jobs:
        # Status indicator with colors (no symbols)
        status_display = job.status.value.upper()
        if job.status == JobStatus.COMPLETED:
            status_style = "success"
        elif job.status == JobStatus.FAILED:
            status_style = "error"
        elif job.status == JobStatus.PROCESSING:
            status_style = "info"
        else:
            status_style = "dim"

        # Truncate prompt
        prompt_preview = job.prompt[:60] + "..." if len(job.prompt) > 60 else job.prompt

        console.print(f"[{status_style}]{status_display:12}[/{status_style}] | {job.id[:12]}... | {job.model}")
        click.echo(f"  {prompt_preview}")

        if job.cost:
            click.echo(f"  Cost: {format_cost(job.cost)}")

        if job.last_error:
            click.echo(f"  Error: {job.last_error[:80]}")

        click.echo()

    click.echo(f"View details: deepr status <job-id>")
    click.echo(f"Get results: deepr get <job-id>")


@click.command()
@click.argument("job_id")
@output_options
def cancel(job_id: str, output_context: OutputContext):
    """[DEPRECATED: Use 'deepr jobs cancel'] Cancel a queued or processing job.

    Examples:
        deepr cancel abc123
        deepr cancel research-1234567890
    """
    if output_context.mode == OutputMode.VERBOSE:
        print_deprecation("deepr cancel <job-id>", "deepr jobs cancel <job-id>")
    asyncio.run(_cancel_job(job_id, output_context))


async def _cancel_job(job_id: str, output_context: Optional[OutputContext] = None):
    """Cancel job.
    
    Args:
        job_id: Job identifier
        output_context: Output formatting context (optional for backward compatibility)
    """
    # Create default output context if not provided (backward compatibility)
    if output_context is None:
        output_context = OutputContext(mode=OutputMode.VERBOSE)
    
    queue = SQLiteQueue()
    job = await queue.get_job(job_id)

    if not job:
        if output_context.mode == OutputMode.JSON:
            print(json.dumps({"status": "error", "error": f"Job not found: {job_id}"}))
        elif output_context.mode != OutputMode.QUIET:
            click.echo(f"Job not found: {job_id}")
        return

    if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
        if output_context.mode == OutputMode.JSON:
            print(json.dumps({"status": "error", "error": f"Job already finished: {job.status.value}"}))
        elif output_context.mode != OutputMode.QUIET:
            click.echo(f"Job already finished: {job.status.value}")
        return

    success = await queue.cancel_job(job.id)

    if output_context.mode == OutputMode.JSON:
        if success:
            print(json.dumps({"status": "success", "job_id": job_id, "message": "Job cancelled"}))
        else:
            print(json.dumps({"status": "error", "error": f"Failed to cancel job: {job_id}"}))
    elif output_context.mode == OutputMode.QUIET:
        pass  # No output in quiet mode
    elif output_context.mode == OutputMode.MINIMAL:
        if success:
            click.echo(f"CANCELLED | {job_id[:12]}")
        else:
            click.echo(f"FAILED | {job_id[:12]} | Could not cancel")
    else:  # VERBOSE
        if success:
            click.echo(f"Job cancelled: {job_id}")
        else:
            click.echo(f"Failed to cancel job: {job_id}")


# Aliases
@click.command(name="s")
@click.argument("job_id")
@output_options
def status_alias(job_id: str, output_context: OutputContext):
    """Quick alias for 'deepr status'."""
    asyncio.run(_show_status(job_id, output_context))


@click.command(name="l")
@click.option("--status-filter", "-s", help="Filter by status")
@click.option("--limit", "-n", type=int, default=10)
@output_options
def list_alias(status_filter: str, limit: int, output_context: OutputContext):
    """Quick alias for 'deepr list'."""
    asyncio.run(_list_jobs(status_filter, limit, output_context))


if __name__ == "__main__":
    status()
