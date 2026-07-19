"""Job polling worker for local deployment."""

import asyncio
import logging
import re
from datetime import datetime
from typing import Any

from ..config import load_config
from ..core.costs import CostController
from ..experts.research_cost_gate import (
    reconcile_research_cost_from_ledger,
    record_unreserved_research_cost,
    refund_research_cost,
    restore_research_cost_reservation,
    settle_research_cost,
)
from ..providers import create_provider
from ..queue import create_queue
from ..services.provider_status import classify_provider_status, terminal_provider_error
from ..storage import create_storage

logger = logging.getLogger(__name__)


def _generate_report_filename(query: str) -> str:
    """Generate a human-readable filename from the research query."""
    slug = query.lower().strip()
    filler_words = [
        "the",
        "a",
        "an",
        "for",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "with",
        "latest",
        "best",
        "create",
        "comprehensive",
        "documentation",
    ]
    words = slug.split()
    words = [w for w in words if w not in filler_words]
    slug = " ".join(words)
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    slug = slug[:50].rstrip("-")
    if len(slug) < 5:
        slug = f"research-{datetime.now().strftime('%Y%m%d-%H%M')}"
    return f"{slug}.md"


class JobPoller:
    """
    Polls provider API for job status updates.

    This is the local-first approach that doesn't require webhooks or ngrok.
    Works reliably on workstations, containers, and cloud deployments.
    """

    def __init__(
        self,
        poll_interval: int = 30,
        socketio: Any = None,
    ) -> None:
        """
        Initialize job poller.

        Args:
            poll_interval: Seconds between polls (default: 30)
            socketio: Optional Socket.IO instance for real-time events
        """
        self.poll_interval = poll_interval
        self.socketio = socketio
        self.running = False

        # Load config
        config = load_config()

        # Initialize components
        self.queue = create_queue(
            config.get("queue", "local"), db_path=config.get("queue_db_path") or "queue/research_queue.db"
        )

        self.storage = create_storage(
            config.get("storage", "local"), base_path=config.get("results_dir") or "data/reports"
        )

        self.provider = create_provider(config.get("provider", "openai"), api_key=config.get("api_key"))

        self.cost_controller = CostController(
            max_cost_per_job=float(config.get("max_cost_per_job", 5.0)),
            max_daily_cost=float(config.get("max_daily_cost", 25.0)),
            max_monthly_cost=float(config.get("max_monthly_cost", 200.0)),
        )

    async def start(self) -> None:
        """Start the polling worker.

        Uses exponential backoff (capped at 5 minutes) when a poll cycle
        raises so a persistent error (e.g., invalid API key, provider
        outage) doesn't hammer the provider every ``poll_interval``
        seconds indefinitely.
        """
        self.running = True
        logger.info(f"Job poller started (interval: {self.poll_interval}s)")
        backoff = self.poll_interval

        while self.running:
            try:
                await self._poll_cycle()
                backoff = self.poll_interval  # reset on success
            except Exception as e:
                from deepr.utils.security import sanitize_log_message

                logger.error("Error in poll cycle: %s", sanitize_log_message(str(e)))
                backoff = min(backoff * 2, 300)

            await asyncio.sleep(backoff)

        logger.info("Job poller stopped")

    async def stop(self) -> None:
        """Stop the polling worker."""
        self.running = False

    async def _poll_cycle(self) -> None:
        """Execute one poll cycle."""
        from ..queue.base import JobStatus

        # Get all processing jobs
        jobs = await self.queue.list_jobs(status=JobStatus.PROCESSING, limit=100)

        if not jobs:
            logger.debug("No active jobs to poll")
            return

        logger.info(f"Polling {len(jobs)} active jobs")

        for job in jobs:
            try:
                await self._check_job_status(job)
            except Exception as e:
                logger.error(f"Error checking job {job.id}: {e}")

    async def _check_job_status(self, job: Any) -> None:
        """Check status of a single job."""
        try:
            if not job.provider_job_id:
                logger.warning(f"Job {job.id} has no provider_job_id, skipping")
                return

            # Get status from provider
            response = await self.provider.get_status(job.provider_job_id)

            provider_status = classify_provider_status(response.status)
            logger.debug("Job %s provider status class: %s", job.id, provider_status)

            # Handle completion
            if provider_status == "completed":
                await self._handle_completion(job, response)

            elif terminal_error := terminal_provider_error(provider_status):
                error = response.error or terminal_error
                await self._handle_failure(job, error)

            elif provider_status == "in_progress":
                logger.debug(f"Job {job.id} still in progress")

            elif provider_status == "queued":
                # Still pending at the provider; nothing to do.
                logger.debug("Job %s still queued at provider", job.id)

            else:
                logger.warning("Job %s returned an unsupported provider status", job.id)

        except Exception as e:
            logger.error(f"Error checking job {job.id}: {e}")
            # Don't mark as failed yet, might be temporary network issue

    async def _handle_completion(self, job: Any, response: Any) -> None:
        """Handle job completion."""
        from ..queue.base import JobStatus

        try:
            logger.info(f"Job {job.id} completed, saving results")

            # Generate query-based filename
            report_filename = _generate_report_filename(job.prompt) if job.prompt else "report.md"

            # Extract content from response
            content = ""
            if response.output:
                for block in response.output:
                    if block.get("type") == "message":
                        for item in block.get("content", []):
                            text = item.get("text", "")
                            if text:
                                content += text + "\n"

            # Save to storage
            await self.storage.save_report(
                job_id=job.id, filename=report_filename, content=content.encode("utf-8"), content_type="text/markdown"
            )

            # Extract cost and tokens
            cost = response.usage.cost if response.usage else 0
            tokens = response.usage.total_tokens if response.usage else 0

            # Update queue with results
            await self.queue.update_results(
                job_id=job.id, report_paths={"markdown": report_filename}, cost=cost, tokens_used=tokens
            )

            # Mark as completed
            await self.queue.update_status(job.id, JobStatus.COMPLETED)

            logger.info(f"Job {job.id} completed successfully (cost: ${cost:.4f})")

        except Exception as e:
            logger.error(f"Error handling completion for job {job.id}: {e}")
            await self._handle_failure(job, str(e))

    async def _handle_failure(self, job: Any, error: str) -> None:
        """Handle job failure."""
        from ..queue.base import JobStatus

        try:
            logger.error(f"Job {job.id} failed: {error}")

            reservation = restore_research_cost_reservation(
                job_id=str(job.id),
                metadata=getattr(job, "metadata", {}),
                provider=str(getattr(job, "provider", "") or ""),
                model=str(getattr(job, "model", "") or ""),
            )
            provider_job_id = getattr(job, "provider_job_id", "")
            provider_job_id = provider_job_id if isinstance(provider_job_id, str) else ""
            if reservation is not None and provider_job_id:
                settle_research_cost(
                    reservation,
                    actual_cost=None,
                    request_id=provider_job_id,
                    source="research_agent.poller._handle_failure",
                )
            elif provider_job_id:
                record_unreserved_research_cost(
                    job_id=str(job.id),
                    provider=str(getattr(job, "provider", "") or ""),
                    model=str(getattr(job, "model", "") or ""),
                    actual_cost=None,
                    request_id=provider_job_id,
                    source="research_agent.poller._handle_failure",
                )
            else:
                refund_research_cost(reservation)
            if provider_job_id and not reconcile_research_cost_from_ledger(reservation, job_id=str(job.id)):
                raise RuntimeError(f"Canonical cost settlement missing for terminal job {job.id}")

            # Update queue with failure status
            await self.queue.update_status(job_id=job.id, status=JobStatus.FAILED, error=error)

        except Exception as e:
            logger.error(f"Error handling failure for job {job.id}: {e}")


async def run_poller(poll_interval: int = 30) -> None:
    """
    Run the job poller.

    This is the main entry point for the worker process.
    """
    poller = JobPoller(poll_interval=poll_interval)

    try:
        await poller.start()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
        await poller.stop()


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # Run poller
    asyncio.run(run_poller())
