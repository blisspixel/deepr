"""Analytics commands - track usage patterns and success metrics."""

import click
from deepr.branding import print_section_header, CHECK, CROSS


@click.group()
def analytics():
    """View usage analytics and success metrics."""
    pass


@analytics.command()
@click.option("--period", "-p",
              type=click.Choice(["today", "week", "month", "all"]),
              default="week",
              help="Time period for analysis")
def report(period: str):
    """
    Generate usage analytics report.

    Shows success rates, model usage, cost trends, and performance metrics.

    Example:
        deepr analytics report
        deepr analytics report --period month
    """
    print_section_header(f"Analytics Report - {period.capitalize()}")

    try:
        import asyncio
        from deepr.queue import create_queue
        from deepr.config import load_config
        from datetime import datetime, timedelta
        from collections import defaultdict

        config = load_config()
        queue = create_queue("local", db_path=config.get("queue_db_path", "queue/research_queue.db"))

        async def get_jobs():
            return await queue.list_jobs(limit=1000)

        all_jobs = asyncio.run(get_jobs())

        # Filter by time period
        now = datetime.utcnow()
        if period == "today":
            cutoff = now - timedelta(days=1)
        elif period == "week":
            cutoff = now - timedelta(days=7)
        elif period == "month":
            cutoff = now - timedelta(days=30)
        else:
            cutoff = None

        jobs = all_jobs
        if cutoff:
            jobs = [j for j in all_jobs if j.submitted_at and j.submitted_at >= cutoff]

        if not jobs:
            click.echo(f"\nNo jobs found for period: {period}")
            return

        # Calculate metrics
        total_jobs = len(jobs)
        completed = sum(1 for j in jobs if j.status.value == "completed")
        failed = sum(1 for j in jobs if j.status.value == "failed")
        processing = sum(1 for j in jobs if j.status.value in ["queued", "processing"])

        success_rate = (completed / total_jobs * 100) if total_jobs > 0 else 0
        failure_rate = (failed / total_jobs * 100) if total_jobs > 0 else 0

        # Cost analysis
        total_cost = sum(getattr(j, 'cost', 0) or 0 for j in jobs)
        completed_cost = sum(getattr(j, 'cost', 0) or 0 for j in jobs if j.status.value == "completed")

        # Model usage
        by_model = defaultdict(lambda: {"count": 0, "completed": 0, "failed": 0, "cost": 0.0})
        for job in jobs:
            model = job.model or "unknown"
            by_model[model]["count"] += 1
            if job.status.value == "completed":
                by_model[model]["completed"] += 1
            elif job.status.value == "failed":
                by_model[model]["failed"] += 1
            by_model[model]["cost"] += getattr(job, 'cost', 0) or 0

        # Time analysis
        completion_times = []
        for job in jobs:
            if job.status.value == "completed" and job.submitted_at and job.completed_at:
                duration = (job.completed_at - job.submitted_at).total_seconds() / 60
                completion_times.append(duration)

        avg_completion_time = sum(completion_times) / len(completion_times) if completion_times else 0

        # Display report
        click.echo(f"\n{'='*60}")
        click.echo(f"  USAGE OVERVIEW")
        click.echo(f"{'='*60}\n")

        click.echo(f"Total Jobs: {total_jobs}")
        click.echo(f"   Completed: {completed} ({success_rate:.1f}%)")
        click.echo(f"   Failed: {failed} ({failure_rate:.1f}%)")
        click.echo(f"   In Progress: {processing}")

        click.echo(f"\n{'='*60}")
        click.echo(f"  COST ANALYSIS")
        click.echo(f"{'='*60}\n")

        click.echo(f"Total Spending: ${total_cost:.2f}")
        click.echo(f"   Completed Jobs: ${completed_cost:.2f}")
        if completed > 0:
            click.echo(f"   Average per Job: ${completed_cost / completed:.2f}")

        click.echo(f"\n{'='*60}")
        click.echo(f"  MODEL PERFORMANCE")
        click.echo(f"{'='*60}\n")

        for model, stats in sorted(by_model.items(), key=lambda x: x[1]["count"], reverse=True):
            model_success = (stats["completed"] / stats["count"] * 100) if stats["count"] > 0 else 0
            click.echo(f"{model}:")
            click.echo(f"   Jobs: {stats['count']} | Success: {model_success:.1f}%")
            click.echo(f"   Cost: ${stats['cost']:.2f}")
            click.echo()

        if completion_times:
            click.echo(f"{'='*60}")
            click.echo(f"  TIMING METRICS")
            click.echo(f"{'='*60}\n")

            click.echo(f"Average Completion Time: {avg_completion_time:.1f} minutes")
            click.echo(f"Fastest: {min(completion_times):.1f} minutes")
            click.echo(f"Slowest: {max(completion_times):.1f} minutes")

        # Recommendations
        click.echo(f"\n{'='*60}")
        click.echo(f"  INSIGHTS")
        click.echo(f"{'='*60}\n")

        if failure_rate > 20:
            click.echo(f"High failure rate detected ({failure_rate:.1f}%)")
            click.echo(f"   Consider reviewing failed jobs for patterns")

        if total_cost > config.get("max_cost_per_month", 1000.0) * 0.8:
            click.echo(f"Approaching monthly budget limit")
            click.echo(f"   Current: ${total_cost:.2f}")
            click.echo(f"   Limit: ${config.get('max_cost_per_month', 1000.0):.2f}")

        cheapest_model = min(by_model.items(), key=lambda x: x[1]["cost"] / x[1]["count"] if x[1]["count"] > 0 else float('inf'))
        if cheapest_model:
            click.echo(f"\nMost cost-effective model: {cheapest_model[0]}")
            avg_cost = cheapest_model[1]["cost"] / cheapest_model[1]["count"]
            click.echo(f"   Average cost: ${avg_cost:.2f} per job")

    except Exception as e:
        click.echo(f"\n{CROSS} Error: {e}", err=True)
        import traceback
        traceback.print_exc()
        raise click.Abort()


@analytics.command()
def trends():
    """
    Show usage trends over time.

    Displays daily job counts and costs for the past week.

    Example:
        deepr analytics trends
    """
    print_section_header("Usage Trends")

    try:
        import asyncio
        from deepr.queue import create_queue
        from deepr.config import load_config
        from datetime import datetime, timedelta
        from collections import defaultdict

        config = load_config()
        queue = create_queue("local", db_path=config.get("queue_db_path", "queue/research_queue.db"))

        async def get_jobs():
            return await queue.list_jobs(limit=1000)

        all_jobs = asyncio.run(get_jobs())

        # Group by day
        now = datetime.utcnow()
        cutoff = now - timedelta(days=7)

        jobs = [j for j in all_jobs if j.submitted_at and j.submitted_at >= cutoff]

        by_day = defaultdict(lambda: {"count": 0, "cost": 0.0, "completed": 0})

        for job in jobs:
            day = job.submitted_at.date()
            by_day[day]["count"] += 1
            by_day[day]["cost"] += getattr(job, 'cost', 0) or 0
            if job.status.value == "completed":
                by_day[day]["completed"] += 1

        # Display
        click.echo(f"\nLast 7 days:\n")
        click.echo(f"{'Date':<12} {'Jobs':<8} {'Completed':<12} {'Cost':<10}")
        click.echo(f"{'-'*12} {'-'*8} {'-'*12} {'-'*10}")

        for i in range(7):
            day = (now - timedelta(days=6-i)).date()
            stats = by_day.get(day, {"count": 0, "cost": 0.0, "completed": 0})
            click.echo(f"{day} {stats['count']:<8} {stats['completed']:<12} ${stats['cost']:<9.2f}")

        total_jobs = sum(s["count"] for s in by_day.values())
        total_cost = sum(s["cost"] for s in by_day.values())

        click.echo(f"{'-'*12} {'-'*8} {'-'*12} {'-'*10}")
        click.echo(f"{'Total':<12} {total_jobs:<8} {'':<12} ${total_cost:<9.2f}")

    except Exception as e:
        click.echo(f"\n{CROSS} Error: {e}", err=True)
        raise click.Abort()


@analytics.command()
def failures():
    """
    Analyze failed jobs to identify patterns.

    Shows common failure reasons and affected models.

    Example:
        deepr analytics failures
    """
    print_section_header("Failure Analysis")

    try:
        import asyncio
        from deepr.queue import create_queue
        from deepr.config import load_config
        from collections import Counter

        config = load_config()
        queue = create_queue("local", db_path=config.get("queue_db_path", "queue/research_queue.db"))

        async def get_jobs():
            return await queue.list_jobs(limit=1000)

        all_jobs = asyncio.run(get_jobs())

        failed_jobs = [j for j in all_jobs if j.status.value == "failed"]

        if not failed_jobs:
            click.echo(f"\n{CHECK} No failed jobs found")
            return

        click.echo(f"\nFound {len(failed_jobs)} failed job(s)\n")

        # Analyze failure reasons
        errors = []
        models = []
        for job in failed_jobs:
            error = getattr(job, 'last_error', None) or "Unknown error"
            errors.append(error[:100])  # Truncate long errors
            models.append(job.model)

        # Count occurrences
        error_counts = Counter(errors)
        model_counts = Counter(models)

        click.echo(f"Most Common Errors:\n")
        for error, count in error_counts.most_common(5):
            click.echo(f"   [{count}x] {error}")

        click.echo(f"\n\nAffected Models:\n")
        for model, count in model_counts.most_common():
            click.echo(f"   {model}: {count} failure(s)")

        click.echo(f"\n\nRecent Failures:\n")
        for job in sorted(failed_jobs, key=lambda j: j.submitted_at, reverse=True)[:5]:
            click.echo(f"   {job.id[:8]}... | {job.model}")
            click.echo(f"   {job.prompt[:60]}...")
            error = getattr(job, 'last_error', 'Unknown')
            click.echo(f"   Error: {error[:80]}")
            click.echo()

    except Exception as e:
        click.echo(f"\n{CROSS} Error: {e}", err=True)
        raise click.Abort()
