"""Queue commands - manage job queue."""

import click

from deepr.cli.async_runner import run_async_command
from deepr.cli.colors import console, print_error, print_section_header, print_success, print_warning


async def _apply_queue_sync_snapshot(*, queue_svc, storage, provider, job, response):
    """Close or advance one local job from a provider status snapshot."""
    from deepr.queue.base import JobStatus
    from deepr.services.provider_completion import reconcile_provider_job
    from deepr.services.provider_status import classify_provider_status, terminal_provider_error

    provider_status = classify_provider_status(response.status)
    if provider_status == "completed" or terminal_provider_error(provider_status):
        updated = await reconcile_provider_job(
            queue=queue_svc,
            storage=storage,
            provider=provider,
            job=job,
            response=response,
            source="cli.queue.sync",
        )
        if updated is not None and updated.status != job.status:
            if updated.status == JobStatus.COMPLETED:
                console.print("   [success]Status changed to COMPLETED[/success]")
            else:
                console.print(f"   [error]Status changed to {updated.status.value.upper()}[/error]")
            return updated
        console.print("   No change")
        return None
    if provider_status == "in_progress" and job.status != JobStatus.PROCESSING:
        console.print("   Status changed to PROCESSING")
        await queue_svc.update_status(job.id, JobStatus.PROCESSING)
        return job
    console.print("   No change")
    return None


@click.group()
def queue():
    """Manage job queue."""
    pass


@queue.command()
@click.option(
    "--status",
    "-s",
    type=click.Choice(["all", "queued", "processing", "completed", "failed"]),
    default="all",
    help="Filter by status",
)
@click.option("--limit", "-n", default=10, help="Max jobs to show")
def list(status: str, limit: int):
    """
    List jobs in queue.

    Example:
        deepr queue list
        deepr queue list --status queued
        deepr queue list --limit 20
    """
    print_section_header("Job Queue")

    try:
        from deepr.config import load_config
        from deepr.queue import create_queue
        from deepr.queue.base import JobStatus

        config = load_config()
        queue_svc = create_queue("local", db_path=config.get("queue_db_path", "queue/research_queue.db"))

        # Get jobs
        async def get_jobs():
            filter_status = None if status == "all" else JobStatus(status)
            return await queue_svc.list_jobs(status=filter_status, limit=limit)

        jobs = run_async_command(get_jobs())

        if not jobs:
            click.echo("\nQueue is empty")
            click.echo('\nSubmit a job: deepr research submit "Your prompt"')
            return

        # Display jobs
        click.echo(f"\nFound {len(jobs)} job(s)\n")

        for job in jobs:
            status_labels = {
                "queued": "QUEUED     ",
                "processing": "PROCESSING ",
                "completed": "COMPLETED  ",
                "failed": "FAILED     ",
            }
            label = status_labels.get(job.status.value, "UNKNOWN    ")

            click.echo(f"{label} | {job.id[:8]}... | {job.model}")
            click.echo(f"           {job.prompt[:80]}{'...' if len(job.prompt) > 80 else ''}")

            if job.cost:
                click.echo(f"           Cost: ${job.cost:.4f}")

            click.echo()

        # Summary
        console.print("View status: deepr research status <job-id>")

    except Exception as e:
        print_error(f"Error: {e}")
        raise click.Abort()


@queue.command()
def stats():
    """
    Show queue statistics.

    Example:
        deepr queue stats
    """
    print_section_header("Queue Statistics")

    try:
        from deepr.config import load_config
        from deepr.queue import create_queue

        config = load_config()
        queue_svc = create_queue("local", db_path=config.get("queue_db_path", "queue/research_queue.db"))

        async def get_stats():
            return await queue_svc.get_queue_stats()

        stats = run_async_command(get_stats())

        console.print("\nJob Statistics:")
        console.print(f"   Total Jobs: {stats['total']}")
        console.print(f"   Queued: {stats['queued']}")
        console.print(f"   Processing: {stats['processing']}")
        console.print(f"   Completed: {stats['completed']}")
        console.print(f"   Failed: {stats['failed']}")

    except Exception as e:
        print_error(f"Error: {e}")
        raise click.Abort()


@queue.command()
@click.option("--status", "-s", type=click.Choice(["pending", "failed"]), default="failed", help="Status to clear")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def clear(status: str, yes: bool):
    """
    Clear jobs from queue by status.

    Example:
        deepr queue clear --status failed
        deepr queue clear --status pending -y
    """
    if not yes:
        if not click.confirm(f"Clear all {status} jobs?"):
            print_warning("Cancelled")
            return

    try:
        from deepr.services.queue import get_queue

        queue_svc = get_queue()

        # Get jobs to clear
        jobs = queue_svc.list_jobs(status=status, limit=1000)

        if not jobs:
            console.print(f"\nNo {status} jobs to clear")
            return

        # Clear jobs
        for job in jobs:
            queue_svc.delete_job(job.id)

        print_success(f"Cleared {len(jobs)} {status} job(s)")

    except Exception as e:
        print_error(f"Error: {e}")
        raise click.Abort()


@queue.command()
@click.option("--interval", "-i", default=30, help="Poll interval in seconds")
def watch(interval: int):
    """
    Watch queue in real-time.

    Example:
        deepr queue watch
        deepr queue watch --interval 10
    """
    import time

    click.echo(f"Watching queue (polling every {interval}s)...")
    click.echo("Press Ctrl+C to stop\n")

    try:
        while True:
            # Clear screen (cross-platform)
            click.clear()

            print_section_header("Queue Watch")

            # Get current stats
            from deepr.services.queue import get_queue

            queue_svc = get_queue()
            jobs = queue_svc.list_jobs(limit=50)

            # Show stats
            pending = sum(1 for j in jobs if j.status.value == "pending")
            in_progress = sum(1 for j in jobs if j.status.value == "in_progress")
            completed = sum(1 for j in jobs if j.status.value == "completed")

            click.echo(f"\nPending: {pending}")
            click.echo(f"In Progress: {in_progress}")
            click.echo(f"Completed: {completed}\n")

            # Show active jobs
            active = [j for j in jobs if j.status.value in ["pending", "in_progress"]]
            if active:
                click.echo("Active Jobs:")
                for job in active[:5]:
                    status = "IN_PROGRESS" if job.status.value == "in_progress" else "PENDING    "
                    click.echo(f"  {status} | {job.id[:8]}... | {job.prompt[:60]}...")
                if len(active) > 5:
                    click.echo(f"  ...and {len(active) - 5} more")

            click.echo(f"\nNext update in {interval}s...")

            time.sleep(interval)

    except KeyboardInterrupt:
        print_success("Stopped watching")


@queue.command()
def sync():
    """
    Sync entire queue with provider - check all pending jobs and update statuses.

    Similar to 'deepr research get --all' but updates local queue status
    for all jobs without downloading results.

    Example:
        deepr queue sync
    """
    print_section_header("Sync Queue with Provider")

    try:
        from deepr.config import load_config
        from deepr.providers import create_provider
        from deepr.queue import create_queue
        from deepr.queue.base import JobStatus
        from deepr.storage import create_storage

        config = load_config()
        queue_svc = create_queue("local", db_path=config.get("queue_db_path", "queue/research_queue.db"))
        storage = create_storage(config.get("storage", "local"), base_path=config.get("results_dir", "data/reports"))

        async def sync_all():
            jobs = await queue_svc.list_jobs()

            # Filter to jobs with provider IDs that aren't in terminal states
            active_jobs = [
                j
                for j in jobs
                if j.provider_job_id and j.status not in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]
            ]

            if not active_jobs:
                click.echo("\nNo active jobs to sync")
                return []

            click.echo(f"\nSyncing {len(active_jobs)} active job(s) with provider...\n")

            synced = []
            for job in active_jobs:
                click.echo(f"Job {job.id[:8]}... | Local: {job.status.value.upper()}")

                try:
                    if job.provider == "gemini":
                        api_key = config.get("gemini_api_key")
                    elif job.provider in ["grok", "xai"]:
                        api_key = config.get("xai_api_key")
                    elif job.provider == "azure":
                        api_key = config.get("azure_api_key")
                    else:
                        api_key = config.get("api_key")
                    provider = create_provider(job.provider, api_key=api_key)
                    # Check status at provider
                    response = await provider.get_status(job.provider_job_id)
                    click.echo(f"                  | Provider: {response.status.upper()}")
                    updated = await _apply_queue_sync_snapshot(
                        queue_svc=queue_svc,
                        storage=storage,
                        provider=provider,
                        job=job,
                        response=response,
                    )
                    if updated is not None:
                        synced.append(updated)

                except Exception as e:
                    console.print(f"   [error]Error: {e}[/error]")

                console.print()

            return synced

        synced = run_async_command(sync_all())

        if synced:
            print_success(f"Synced {len(synced)} job(s)")
            console.print("\nTo download results: deepr research get --all")
        else:
            console.print("\nAll jobs already in sync")

    except Exception as e:
        print_error(f"Error: {e}")
        import traceback

        traceback.print_exc()
        raise click.Abort()
