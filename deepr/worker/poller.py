"""Job polling worker for local deployment."""

import asyncio
import logging

from ..config import load_config
from ..core.costs import CostController
from ..providers import create_provider
from ..queue import create_queue
from ..storage import create_storage

logger = logging.getLogger(__name__)


class JobPoller:
    """
    Polls provider API for job status updates.

    This is the local-first approach that doesn't require webhooks or ngrok.
    Works reliably on workstations, containers, and cloud deployments.
    """

    def __init__(
        self,
        poll_interval: int = 30,
        socketio=None,
    ):
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
            config.get("queue", "local"), db_path=config.get("queue_db_path", "queue/research_queue.db")
        )

        self.storage = create_storage(config.get("storage", "local"), base_path=config.get("results_dir", "results"))

        self.provider = create_provider(config.get("provider", "openai"), api_key=config.get("api_key"))

        self.cost_controller = CostController(
            max_cost_per_job=float(config.get("max_cost_per_job", 5.0)),
            max_daily_cost=float(config.get("max_daily_cost", 25.0)),
            max_monthly_cost=float(config.get("max_monthly_cost", 200.0)),
        )

    async def start(self):
        """Start the polling worker."""
        self.running = True
        logger.info(f"Job poller started (interval: {self.poll_interval}s)")

        while self.running:
            try:
                await self._poll_cycle()
            except Exception as e:
                logger.error(f"Error in poll cycle: {e}")

            await asyncio.sleep(self.poll_interval)

        logger.info("Job poller stopped")

    async def stop(self):
        """Stop the polling worker."""
        self.running = False

    async def _poll_cycle(self):
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

    async def _check_job_status(self, job):
        """Check status of a single job."""
        from datetime import datetime, timezone

        try:
            if not job.provider_job_id:
                logger.warning(f"Job {job.id} has no provider_job_id, skipping")
                return

            # Get status from provider
            response = await self.provider.get_status(job.provider_job_id)

            logger.debug(f"Job {job.id} provider status: {response.status}")

            # Handle completion
            if response.status == "completed":
                await self._handle_completion(job, response)

            # Handle failure
            elif response.status == "failed":
                error = response.error or "Job failed"
                await self._handle_failure(job, error)

            # Update progress if available (in_progress stays as is)
            elif response.status == "in_progress":
                logger.debug(f"Job {job.id} still in progress")

            # Check for stuck jobs in "queued" status
            elif response.status == "queued":
                # Calculate time in queue
                if job.submitted_at:
                    submitted = job.submitted_at
                    if not submitted.tzinfo:
                        submitted = submitted.replace(tzinfo=timezone.utc)
                    now = datetime.now(timezone.utc)
                    queue_time_minutes = (now - submitted).total_seconds() / 60

                    # If queued for more than 10 minutes, consider it stuck
                    if queue_time_minutes > 10:
                        logger.warning(
                            f"Job {job.id} stuck in queue for {queue_time_minutes:.1f} minutes. "
                            f"Cancelling and marking as failed."
                        )

                        # Try to cancel at provider
                        try:
                            await self.provider.cancel_job(job.provider_job_id)
                            logger.info(f"Cancelled stuck job {job.id} at provider")
                        except Exception as cancel_error:
                            logger.warning(f"Could not cancel at provider: {cancel_error}")

                        # Mark as failed in queue
                        await self._handle_failure(
                            job, f"Job stuck in provider queue for {queue_time_minutes:.1f} minutes - auto-cancelled"
                        )
                    else:
                        logger.debug(f"Job {job.id} queued for {queue_time_minutes:.1f} minutes")

        except Exception as e:
            logger.error(f"Error checking job {job.id}: {e}")
            # Don't mark as failed yet, might be temporary network issue

    async def _handle_completion(self, job, response):
        """Handle job completion."""
        from ..queue.base import JobStatus

        try:
            logger.info(f"Job {job.id} completed, saving results")

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
                job_id=job.id,
                filename="report.md",
                content=content.encode("utf-8"),
                content_type="text/markdown",
                metadata={
                    "prompt": job.prompt,
                    "model": job.model,
                    "status": "completed",
                    "provider_job_id": job.provider_job_id,
                },
            )

            # Extract cost and tokens
            cost = response.usage.cost if response.usage else 0
            tokens = response.usage.total_tokens if response.usage else 0

            # Update queue with results
            await self.queue.update_results(
                job_id=job.id, report_paths={"markdown": "report.md"}, cost=cost, tokens_used=tokens
            )

            # Mark as completed
            await self.queue.update_status(job.id, JobStatus.COMPLETED)

            logger.info(f"Job {job.id} completed successfully (cost: ${cost:.4f})")

        except Exception as e:
            logger.error(f"Error handling completion for job {job.id}: {e}")
            await self._handle_failure(job, str(e))

    async def _handle_failure(self, job, error: str):
        """Handle job failure."""
        from ..queue.base import JobStatus

        try:
            logger.error(f"Job {job.id} failed: {error}")

            # Update queue with failure status
            await self.queue.update_status(job_id=job.id, status=JobStatus.FAILED, error=error)

        except Exception as e:
            logger.error(f"Error handling failure for job {job.id}: {e}")


async def run_poller(poll_interval: int = 30):
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
