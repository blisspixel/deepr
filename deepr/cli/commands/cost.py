"""Cost commands - estimate and track costs."""

import click

from deepr.cli.colors import console, print_error, print_section_header


@click.group()
def cost():
    """Estimate and track research costs."""
    pass


@cost.command()
@click.argument("prompt")
@click.option(
    "--model",
    "-m",
    default="o4-mini-deep-research",
    type=click.Choice(["o4-mini-deep-research", "o3-deep-research"]),
    help="Research model",
)
@click.option("--web-search/--no-web-search", default=True, help="Enable web search")
def estimate(prompt: str, model: str, web_search: bool):
    """
    Estimate cost for a research prompt.

    Example:
        deepr cost estimate "What are AI trends?"
        deepr cost estimate "Kubernetes guide" --model o3-deep-research
    """
    print_section_header("Cost Estimation")

    try:
        from deepr.services.cost_estimation import CostEstimator

        estimate = CostEstimator.estimate_cost(prompt=prompt, model=model, enable_web_search=web_search)

        console.print("\nCost Estimate:")
        console.print(f"   Expected: ${estimate.expected_cost:.2f}")
        console.print(f"   Min: ${estimate.min_cost:.2f}")
        console.print(f"   Max: ${estimate.max_cost:.2f}")

        console.print("\nConfiguration:")
        console.print(f"   Model: {model}")
        console.print(f"   Web Search: {'enabled' if web_search else 'disabled'}")
        console.print(f"   Prompt length: {len(prompt)} chars")

    except Exception as e:
        print_error(f"Error: {e}")
        raise click.Abort()


@cost.command()
@click.option(
    "--period",
    "-p",
    type=click.Choice(["today", "week", "month", "all"]),
    default="all",
    help="Time period for summary",
)
def summary(period: str):
    """
    Show cost summary and budget status.

    Example:
        deepr cost summary
        deepr cost summary --period today
        deepr cost summary --period week
    """
    print_section_header(f"Cost Summary - {period.capitalize()}")

    try:
        import asyncio
        from datetime import datetime, timedelta, timezone

        from deepr.config import load_config
        from deepr.queue import create_queue

        config = load_config()
        queue = create_queue("local", db_path=config.get("queue_db_path", "queue/research_queue.db"))

        async def get_jobs():
            return await queue.list_jobs(limit=1000)

        all_jobs = asyncio.run(get_jobs())

        # Filter by time period
        now = datetime.now(timezone.utc)
        if period == "today":
            cutoff = now - timedelta(days=1)
        elif period == "week":
            cutoff = now - timedelta(days=7)
        elif period == "month":
            cutoff = now - timedelta(days=30)
        else:
            cutoff = None

        filtered_jobs = all_jobs
        if cutoff:
            filtered_jobs = [j for j in all_jobs if j.submitted_at and j.submitted_at >= cutoff]

        if not filtered_jobs:
            click.echo(f"\nNo jobs found for period: {period}")
            return

        # Calculate costs
        total_cost = 0.0
        completed_cost = 0.0
        pending_cost = 0.0
        failed_cost = 0.0

        # Track by model
        by_model = {}

        for job in filtered_jobs:
            cost = getattr(job, "cost", None) or getattr(job, "estimated_cost", 0)
            total_cost += cost

            # Track by model
            model = job.model or "unknown"
            if model not in by_model:
                by_model[model] = {"count": 0, "cost": 0.0}
            by_model[model]["count"] += 1
            by_model[model]["cost"] += cost

            if job.status.value == "completed":
                completed_cost += cost
            elif job.status.value in ["queued", "processing"]:
                pending_cost += cost
            elif job.status.value == "failed":
                failed_cost += cost

        completed_jobs = sum(1 for j in filtered_jobs if j.status.value == "completed")
        avg_cost = completed_cost / completed_jobs if completed_jobs > 0 else 0

        # Display summary
        click.echo(f"\nTotal Spending: ${total_cost:.2f}")
        click.echo(f"   Completed: ${completed_cost:.2f} ({completed_jobs} jobs)")
        click.echo(f"   Pending: ${pending_cost:.2f}")
        if failed_cost > 0:
            click.echo(f"   Failed: ${failed_cost:.2f}")

        if completed_jobs > 0:
            click.echo("\nStatistics:")
            click.echo(f"   Total Jobs: {len(filtered_jobs)}")
            click.echo(f"   Completed: {completed_jobs}")
            click.echo(f"   Average per job: ${avg_cost:.2f}")

        # Show breakdown by model
        if by_model:
            click.echo("\nBy Model:")
            for model, data in sorted(by_model.items(), key=lambda x: x[1]["cost"], reverse=True):
                click.echo(f"   {model}: ${data['cost']:.2f} ({data['count']} jobs)")

        # Budget check
        max_per_month = config.get("max_cost_per_month", 1000.0)
        max_per_day = config.get("max_cost_per_day", 100.0)

        if period == "month":
            pct = (total_cost / max_per_month) * 100
            click.echo("\nMonthly Budget:")
            click.echo(f"   Used: ${total_cost:.2f} / ${max_per_month:.2f} ({pct:.1f}%)")
        elif period == "today":
            pct = (total_cost / max_per_day) * 100
            console.print("\nDaily Budget:")
            console.print(f"   Used: ${total_cost:.2f} / ${max_per_day:.2f} ({pct:.1f}%)")

    except Exception as e:
        print_error(f"Error: {e}")
        raise click.Abort()
