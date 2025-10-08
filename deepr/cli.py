"""
Command-line interface for Deepr v2.

Simple CLI for testing v2 components.
"""

import sys
import asyncio
import argparse
import os
from pathlib import Path
from typing import Optional
from .providers import create_provider
from .storage import create_storage
from .queue import create_queue
from .core.costs import CostEstimator, CostController, CHEAP_TEST_PROMPTS
from .queue.base import ResearchJob
from .branding import print_banner, print_section_header


class DeeprCLI:
    """Command-line interface for Deepr."""

    def __init__(self):
        """Initialize CLI with simple configuration from environment."""
        # Provider
        provider_type = os.getenv("DEEPR_PROVIDER", "openai")
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("AZURE_OPENAI_API_KEY")

        if not api_key:
            raise ValueError(
                "API key required. Set OPENAI_API_KEY or AZURE_OPENAI_API_KEY"
            )

        self.provider = create_provider(provider_type, api_key=api_key)

        # Storage
        storage_type = os.getenv("DEEPR_STORAGE", "local")
        results_dir = os.getenv("DEEPR_RESULTS_DIR", "results")
        self.storage = create_storage(storage_type, base_path=results_dir)

        # Queue
        queue_type = os.getenv("DEEPR_QUEUE", "local")
        queue_db = os.getenv("DEEPR_QUEUE_DB_PATH", "queue/research_queue.db")
        self.queue = create_queue(queue_type, db_path=queue_db)

        # Cost controller
        max_per_job = float(os.getenv("DEEPR_MAX_COST_PER_JOB", "10.0"))
        max_per_day = float(os.getenv("DEEPR_MAX_COST_PER_DAY", "100.0"))
        max_per_month = float(os.getenv("DEEPR_MAX_COST_PER_MONTH", "1000.0"))

        self.cost_controller = CostController(
            max_cost_per_job=max_per_job,
            max_daily_cost=max_per_day,
            max_monthly_cost=max_per_month,
        )

        self.default_model = os.getenv(
            "DEEPR_DEFAULT_MODEL", "o4-mini-deep-research"
        )
        self.enable_web_search = os.getenv("DEEPR_ENABLE_WEB_SEARCH", "true").lower() == "true"

    async def status(self):
        """Display system status and configuration."""
        print_banner("main")
        print_section_header("System Status")
        print(f"Provider:      {type(self.provider).__name__}")
        print(f"Storage:       {type(self.storage).__name__}")
        print(f"Queue:         {type(self.queue).__name__}")
        print(f"Default Model: {self.default_model}")
        print(f"Web Search:    {'enabled' if self.enable_web_search else 'disabled'}")
        print()
        print("Cost Limits:")
        print(f"  Per Job:    ${self.cost_controller.max_cost_per_job:.2f}")
        print(f"  Per Day:    ${self.cost_controller.max_daily_cost:.2f}")
        print(f"  Per Month:  ${self.cost_controller.max_monthly_cost:.2f}")
        print()

        # Queue stats
        stats = await self.queue.get_queue_stats()
        print("Queue Statistics:")
        print(f"  Pending:    {stats.get('pending', 0)}")
        print(f"  Processing: {stats.get('in_progress', 0)}")
        print(f"  Completed:  {stats.get('completed', 0)}")
        print(f"  Failed:     {stats.get('failed', 0)}")
        print()

        # Spending summary
        summary = self.cost_controller.get_spending_summary()
        print("Spending Summary:")
        print(f"  Daily:      ${summary['daily']:.2f} / ${summary['daily_limit']:.2f}")
        print(f"  Monthly:    ${summary['monthly']:.2f} / ${summary['monthly_limit']:.2f}")
        print()

    async def research(
        self,
        prompt: str,
        model: Optional[str] = None,
        priority: int = 1,
        enable_web_search: Optional[bool] = None,
    ):
        """
        Submit a research job to the queue.

        Args:
            prompt: Research prompt/question
            model: Model to use (default from config)
            priority: Job priority (1=high, 5=low)
            enable_web_search: Enable web search (default from config)
        """
        model = model or self.default_model
        enable_web_search = (
            enable_web_search
            if enable_web_search is not None
            else self.enable_web_search
        )

        print(f"Submitting research job...")
        print(f"  Prompt: {prompt[:100]}...")
        print(f"  Model: {model}")
        print(f"  Web Search: {'enabled' if enable_web_search else 'disabled'}")
        print()

        # Estimate cost
        estimate = CostEstimator.estimate_cost(
            prompt=prompt,
            model=model,
            enable_web_search=enable_web_search,
        )

        print(f"Cost Estimate:")
        print(f"  Expected: ${estimate.expected_cost:.2f}")
        print(f"  Range: ${estimate.min_cost:.2f} - ${estimate.max_cost:.2f}")
        print()

        # Check cost limits
        allowed, reason = self.cost_controller.check_job_limit(estimate.expected_cost)
        if not allowed:
            print(f"ERROR: {reason}")
            return 1

        # Create job
        job = ResearchJob(
            prompt=prompt,
            model=model,
            priority=priority,
            enable_web_search=enable_web_search,
            estimated_cost=estimate.expected_cost,
        )

        # Enqueue
        await self.queue.enqueue(job)

        print(f"Job submitted successfully")
        print(f"  Job ID: {job.id}")
        print(f"  Status: {job.status}")
        print(f"  Priority: {job.priority}")
        print()
        print(f"Use: python -m deepr.cli get {job.id}")

        return 0

    async def get(self, job_id: str):
        """Get details about a specific job."""
        job = await self.queue.get_job(job_id)

        if not job:
            print(f"ERROR: Job {job_id} not found")
            return 1

        print(f"Job Details: {job_id}")
        print("=" * 60)
        print(f"Status:        {job.status}")
        print(f"Priority:      {job.priority}")
        print(f"Model:         {job.model}")
        print(f"Web Search:    {'enabled' if job.enable_web_search else 'disabled'}")
        print(f"Created:       {job.created_at}")
        print(f"Updated:       {job.updated_at}")
        print()
        print(f"Prompt:")
        print(f"  {job.prompt[:200]}...")
        print()

        if job.estimated_cost:
            print(f"Estimated Cost: ${job.estimated_cost:.2f}")

        if job.actual_cost:
            print(f"Actual Cost:    ${job.actual_cost:.2f}")

        print()
        return 0

    async def list(self, status: Optional[str] = None, limit: int = 10):
        """List jobs in the queue."""
        jobs = await self.queue.list_jobs(status=status, limit=limit)

        if not jobs:
            print("No jobs found")
            return 0

        print(f"Jobs ({len(jobs)} shown):")
        print("=" * 60)
        print()

        for job in jobs:
            status_display = job.status.upper() if job.status else "UNKNOWN"
            print(f"[{status_display}] {job.id}")
            print(f"   Model: {job.model}")
            print(f"   Prompt: {job.prompt[:80]}...")
            print(f"   Created: {job.created_at}")
            if job.estimated_cost:
                print(f"   Est. Cost: ${job.estimated_cost:.2f}")
            print()

        return 0

    async def cancel(self, job_id: str):
        """Cancel a pending or in-progress job."""
        success = await self.queue.cancel_job(job_id)

        if success:
            print(f"Job {job_id} cancelled successfully")
            return 0
        else:
            print(f"ERROR: Failed to cancel job {job_id}")
            return 1

    async def test(self, index: int = 0):
        """Submit a cheap test prompt for validation."""
        if index < 0 or index >= len(CHEAP_TEST_PROMPTS):
            print(f"ERROR: Index must be 0-{len(CHEAP_TEST_PROMPTS)-1}")
            return 1

        test_prompt = CHEAP_TEST_PROMPTS[index]

        print(f"Submitting test prompt (index {index}):")
        print(f"  {test_prompt['description']}")
        print(f"  Expected cost: ${test_prompt['expected_cost']:.2f}")
        print()

        return await self.research(
            prompt=test_prompt["prompt"],
            model="o4-mini-deep-research",
            enable_web_search=False,
        )


def main():
    """Main CLI entry point."""
    # Show banner on help or no command
    if len(sys.argv) == 1 or (len(sys.argv) == 2 and sys.argv[1] in ['-h', '--help']):
        print_banner("main")

    parser = argparse.ArgumentParser(
        description="Deepr v2 - Deep Research Automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # status command
    subparsers.add_parser("status", help="Show system status")

    # research command
    research_parser = subparsers.add_parser("research", help="Submit research job")
    research_parser.add_argument("prompt", help="Research prompt/question")
    research_parser.add_argument("--model", help="Model to use")
    research_parser.add_argument(
        "--priority", type=int, default=1, help="Job priority (1=high, 5=low)"
    )
    research_parser.add_argument(
        "--no-web-search", action="store_true", help="Disable web search"
    )

    # get command
    get_parser = subparsers.add_parser("get", help="Get job details")
    get_parser.add_argument("job_id", help="Job ID")

    # list command
    list_parser = subparsers.add_parser("list", help="List jobs")
    list_parser.add_argument("--status", help="Filter by status")
    list_parser.add_argument("--limit", type=int, default=10, help="Max jobs to show")

    # cancel command
    cancel_parser = subparsers.add_parser("cancel", help="Cancel job")
    cancel_parser.add_argument("job_id", help="Job ID to cancel")

    # test command
    test_parser = subparsers.add_parser("test", help="Submit test prompt")
    test_parser.add_argument(
        "--index", type=int, default=0, help="Test prompt index (0-5)"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Create CLI instance
    try:
        cli = DeeprCLI()
    except ValueError as e:
        print(f"Configuration error: {e}")
        print()
        print("Make sure to set required environment variables:")
        print("  OPENAI_API_KEY or AZURE_OPENAI_API_KEY")
        return 1

    # Run command
    try:
        if args.command == "status":
            result = asyncio.run(cli.status())
        elif args.command == "research":
            result = asyncio.run(
                cli.research(
                    prompt=args.prompt,
                    model=args.model,
                    priority=args.priority,
                    enable_web_search=not args.no_web_search,
                )
            )
        elif args.command == "get":
            result = asyncio.run(cli.get(args.job_id))
        elif args.command == "list":
            result = asyncio.run(cli.list(status=args.status, limit=args.limit))
        elif args.command == "cancel":
            result = asyncio.run(cli.cancel(args.job_id))
        elif args.command == "test":
            result = asyncio.run(cli.test(index=args.index))
        else:
            parser.print_help()
            return 1

        return result or 0

    except KeyboardInterrupt:
        print("\nInterrupted")
        return 130
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
