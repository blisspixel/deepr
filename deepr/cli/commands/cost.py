"""Cost commands - estimate and track costs."""

import click
from deepr.branding import print_section_header, CHECK


@click.group()
def cost():
    """Estimate and track research costs."""
    pass


@cost.command()
@click.argument("prompt")
@click.option("--model", "-m", default="o4-mini-deep-research",
              type=click.Choice(["o4-mini-deep-research", "o3-deep-research"]),
              help="Research model")
@click.option("--web-search/--no-web-search", default=True,
              help="Enable web search")
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

        estimate = CostEstimator.estimate_cost(
            prompt=prompt,
            model=model,
            enable_web_search=web_search
        )

        click.echo(f"\nCost Estimate:")
        click.echo(f"   Expected: ${estimate.expected_cost:.2f}")
        click.echo(f"   Min: ${estimate.min_cost:.2f}")
        click.echo(f"   Max: ${estimate.max_cost:.2f}")

        click.echo(f"\nConfiguration:")
        click.echo(f"   Model: {model}")
        click.echo(f"   Web Search: {'enabled' if web_search else 'disabled'}")
        click.echo(f"   Prompt length: {len(prompt)} chars")

    except Exception as e:
        from deepr.branding import CROSS
        click.echo(f"\n{CROSS} Error: {e}", err=True)
        raise click.Abort()


@cost.command()
def summary():
    """
    Show cost summary and budget status.

    Example:
        deepr cost summary
    """
    print_section_header("Cost Summary")

    try:
        from deepr.services.queue import get_queue

        queue = get_queue()
        all_jobs = queue.list_jobs(limit=1000)

        # Calculate costs
        total_cost = 0.0
        completed_cost = 0.0
        pending_cost = 0.0

        for job in all_jobs:
            cost = getattr(job, 'actual_cost', None) or getattr(job, 'estimated_cost', 0)
            total_cost += cost

            if job.status.value == "completed":
                completed_cost += cost
            elif job.status.value in ["pending", "in_progress"]:
                pending_cost += cost

        completed_jobs = sum(1 for j in all_jobs if j.status.value == "completed")
        avg_cost = completed_cost / completed_jobs if completed_jobs > 0 else 0

        click.echo(f"\nTotal Spending: ${total_cost:.2f}")
        click.echo(f"   Completed: ${completed_cost:.2f}")
        click.echo(f"   Pending: ${pending_cost:.2f}")

        if completed_jobs > 0:
            click.echo(f"\nStatistics:")
            click.echo(f"   Completed Jobs: {completed_jobs}")
            click.echo(f"   Average per job: ${avg_cost:.2f}")

        # Budget check (if configured)
        click.echo(f"\nConfigure limits: Edit config/deepr.yaml")

    except Exception as e:
        from deepr.branding import CROSS
        click.echo(f"\n{CROSS} Error: {e}", err=True)
        raise click.Abort()
