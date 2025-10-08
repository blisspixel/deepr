"""Queue commands - manage job queue."""

import click
from typing import Optional
from deepr.branding import print_section_header, CHECK, CROSS


@click.group()
def queue():
    """Manage job queue."""
    pass


@queue.command()
@click.option("--status", "-s",
              type=click.Choice(["all", "queued", "processing", "completed", "failed"]),
              default="all", help="Filter by status")
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
        import asyncio
        from deepr.queue import create_queue
        from deepr.queue.base import JobStatus
        from deepr.config import load_config

        config = load_config()
        queue_svc = create_queue("local", db_path=config.get("queue_db_path", "queue/research_queue.db"))

        # Get jobs
        async def get_jobs():
            filter_status = None if status == "all" else JobStatus(status)
            return await queue_svc.list_jobs(status=filter_status, limit=limit)

        jobs = asyncio.run(get_jobs())

        if not jobs:
            click.echo(f"\nQueue is empty")
            click.echo(f"\nSubmit a job: deepr research submit \"Your prompt\"")
            return

        # Display jobs
        click.echo(f"\nFound {len(jobs)} job(s)\n")

        for job in jobs:
            status_labels = {
                "queued": "QUEUED     ",
                "processing": "PROCESSING ",
                "completed": "COMPLETED  ",
                "failed": "FAILED     "
            }
            label = status_labels.get(job.status.value, "UNKNOWN    ")

            click.echo(f"{label} | {job.id[:8]}... | {job.model}")
            click.echo(f"           {job.prompt[:80]}{'...' if len(job.prompt) > 80 else ''}")

            if job.cost:
                click.echo(f"           Cost: ${job.cost:.4f}")

            click.echo()

        # Summary
        click.echo(f"View status: deepr research status <job-id>")

    except Exception as e:
        click.echo(f"\n{CROSS} Error: {e}", err=True)
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
        import asyncio
        from deepr.queue import create_queue
        from deepr.config import load_config

        config = load_config()
        queue_svc = create_queue("local", db_path=config.get("queue_db_path", "queue/research_queue.db"))

        async def get_stats():
            return await queue_svc.get_queue_stats()

        stats = asyncio.run(get_stats())

        click.echo(f"\nJob Statistics:")
        click.echo(f"   Total Jobs: {stats['total']}")
        click.echo(f"   Queued: {stats['queued']}")
        click.echo(f"   Processing: {stats['processing']}")
        click.echo(f"   Completed: {stats['completed']}")
        click.echo(f"   Failed: {stats['failed']}")

    except Exception as e:
        click.echo(f"\n{CROSS} Error: {e}", err=True)
        raise click.Abort()


@queue.command()
@click.option("--status", "-s",
              type=click.Choice(["pending", "failed"]),
              default="failed", help="Status to clear")
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
            click.echo(f"\n{CROSS} Cancelled")
            return

    try:
        from deepr.services.queue import get_queue

        queue_svc = get_queue()

        # Get jobs to clear
        jobs = queue_svc.list_jobs(status=status, limit=1000)

        if not jobs:
            click.echo(f"\nNo {status} jobs to clear")
            return

        # Clear jobs
        for job in jobs:
            queue_svc.delete_job(job.id)

        click.echo(f"\n{CHECK} Cleared {len(jobs)} {status} job(s)")

    except Exception as e:
        click.echo(f"\n{CROSS} Error: {e}", err=True)
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
        click.echo(f"\n\n{CHECK} Stopped watching")
