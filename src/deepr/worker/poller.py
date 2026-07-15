"""Job polling worker for local deployment."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from ..config import load_config
from ..core.costs import CostController
from ..experts.research_cost_gate import (
    ResearchCostReservation,
    reconcile_research_cost_from_ledger,
    record_unreserved_research_cost,
    refund_research_cost,
    restore_research_cost_reservation,
    settle_research_cost,
)
from ..providers import create_provider
from ..providers.base import DeepResearchProvider, ResearchResponse
from ..queue import create_queue
from ..queue.base import JobStatus, QueueBackend, ResearchJob
from ..services.provider_status import (
    classify_provider_status,
    provider_exception_name,
    terminal_provider_error,
)
from ..storage import create_storage
from ..storage.base import StorageBackend

logger = logging.getLogger(__name__)
_MAX_CONCURRENT_POLLS = 8


def _response_content(response: ResearchResponse) -> str:
    """Collect text blocks from a completed provider response."""
    chunks: list[str] = []
    for block in response.output or []:
        if block.get("type") != "message":
            continue
        for item in block.get("content", []):
            if text := item.get("text", ""):
                chunks.append(text)
    return "\n".join(chunks) + ("\n" if chunks else "")


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
        queue: QueueBackend | None = None,
        provider: DeepResearchProvider | None = None,
        storage: StorageBackend | None = None,
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
        self._in_flight_job_ids: set[str] = set()
        # CostController.record_cost is not idempotent; completion retries must
        # not re-add the same job's spend to in-process daily/monthly totals.
        self._cost_controller_recorded_job_ids: set[str] = set()

        # Load config
        config = load_config()

        # Initialize components
        self.queue: QueueBackend = queue or create_queue(
            config.get("queue", "local"), db_path=config.get("queue_db_path") or "queue/research_queue.db"
        )

        self.storage: StorageBackend = storage or create_storage(
            config.get("storage", "local"), base_path=config.get("results_dir") or "data/reports"
        )

        self.provider: DeepResearchProvider = provider or create_provider(
            config.get("provider", "openai"), api_key=config.get("api_key")
        )

        self.cost_controller = CostController(
            max_cost_per_job=float(config.get("max_cost_per_job", 5.0)),
            max_daily_cost=float(config.get("max_daily_cost", 25.0)),
            max_monthly_cost=float(config.get("max_monthly_cost", 200.0)),
        )

    async def start(self) -> None:
        """Start the polling worker."""
        self.running = True
        logger.info(f"Job poller started (interval: {self.poll_interval}s)")

        while self.running:
            try:
                await self._poll_cycle()
            except Exception as exc:
                from deepr.utils.security import sanitize_log_message

                logger.error("Error in poll cycle: %s", sanitize_log_message(str(exc)))

            await asyncio.sleep(self.poll_interval)

        logger.info("Job poller stopped")

    async def stop(self) -> None:
        """Stop the polling worker."""
        self.running = False

    async def _poll_cycle(self) -> None:
        """Execute one poll cycle."""
        # Page through every PROCESSING job. A single limit=100 newest-first
        # slice starved older jobs once the backlog exceeded one page.
        page_size = 100
        jobs: list[ResearchJob] = []
        page_offset = 0
        while True:
            page = await self.queue.list_jobs(
                status=JobStatus.PROCESSING,
                limit=page_size,
                offset=page_offset,
            )
            if not page:
                break
            jobs.extend(page)
            if len(page) < page_size:
                break
            page_offset += page_size

        if not jobs:
            logger.debug("No active jobs to poll")
            return

        unique_jobs: list[ResearchJob] = []
        seen_job_ids: set[str] = set()
        for job in jobs:
            job_id = str(job.id)
            if job_id in seen_job_ids:
                logger.warning("Ignoring duplicate active job %s in one poll cycle", job_id)
                continue
            seen_job_ids.add(job_id)
            unique_jobs.append(job)

        logger.info("Polling %s active jobs", len(unique_jobs))
        for offset in range(0, len(unique_jobs), _MAX_CONCURRENT_POLLS):
            batch = unique_jobs[offset : offset + _MAX_CONCURRENT_POLLS]
            await asyncio.gather(*(self._poll_job(job) for job in batch))

    async def _poll_job(self, job: ResearchJob) -> None:
        """Check one job while isolating non-cancellation failures."""
        try:
            await self.check_job_status(job)
        except Exception:
            logger.exception("Error checking job %s", job.id)

    async def check_job_status(self, job: ResearchJob) -> None:
        """Poll one job unless the same job is already in flight."""
        job_id = str(job.id)
        if job_id in self._in_flight_job_ids:
            logger.debug("Job %s already has a status check in flight", job_id)
            return
        self._in_flight_job_ids.add(job_id)
        try:
            await self._check_job_status(job)
        finally:
            self._in_flight_job_ids.discard(job_id)

    async def _check_job_status(self, job: ResearchJob) -> None:
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
                if provider_status == "cancelled":
                    await self._handle_failure(job, terminal_error, status=JobStatus.CANCELLED)
                else:
                    await self._handle_failure(job, terminal_error)

            elif provider_status == "unsupported":
                logger.warning("Job %s returned an unsupported provider status", job.id)

            # Update progress if available (in_progress stays as is)
            elif provider_status == "in_progress":
                logger.debug(f"Job {job.id} still in progress")

            # Check for stuck jobs in "queued" status
            elif provider_status == "queued":
                await self._handle_queued_job(job)

        except Exception as exc:
            logger.warning(
                "Provider status check failed for job %s (%s)",
                job.id,
                provider_exception_name(exc),
            )
            # Don't mark as failed yet, might be temporary network issue

    async def _handle_queued_job(self, job: ResearchJob) -> None:
        """Cancel a provider job only after it has remained queued too long."""
        provider_job_id = job.provider_job_id
        if not job.submitted_at or not provider_job_id:
            return

        submitted = job.submitted_at
        if not submitted.tzinfo:
            submitted = submitted.replace(tzinfo=UTC)
        queue_time_minutes = (datetime.now(UTC) - submitted).total_seconds() / 60
        if queue_time_minutes <= 10:
            logger.debug("Job %s queued for %.1f minutes", job.id, queue_time_minutes)
            return

        logger.warning(
            "Job %s stuck in queue for %.1f minutes. Cancelling and marking as failed.",
            job.id,
            queue_time_minutes,
        )
        try:
            cancelled = bool(await self.provider.cancel_job(provider_job_id))
        except Exception:
            cancelled = False
            logger.warning("Could not cancel job %s at provider", job.id)

        if not cancelled:
            logger.warning("Provider did not confirm cancellation for stuck job %s", job.id)
            logger.warning("Retaining stuck job %s for later polling", job.id)
            return

        logger.info("Cancelled stuck job %s at provider", job.id)
        await self._handle_failure(
            job,
            f"Job stuck in provider queue for {queue_time_minutes:.1f} minutes - auto-cancelled",
        )

    def _record_completion_cost(
        self,
        job: ResearchJob,
        *,
        cost: float | None,
        tokens: int,
    ) -> ResearchCostReservation | None:
        """Update both cost observers while retaining retry-safe reservation state."""
        try:
            job_key = str(job.id)
            if job_key not in self._cost_controller_recorded_job_ids:
                self.cost_controller.record_cost(actual_cost=float(cost or 0))
                self._cost_controller_recorded_job_ids.add(job_key)
        except Exception:
            logger.debug("CostController.record_cost failed for job %s", job.id, exc_info=True)

        reservation: ResearchCostReservation | None = None
        try:
            reservation = restore_research_cost_reservation(
                job_id=job.id,
                metadata=job.metadata,
                provider=getattr(job, "provider", "") or "",
                model=job.model,
            )
            if reservation is not None:
                settle_research_cost(
                    reservation,
                    actual_cost=cost,
                    tokens=tokens,
                    request_id=job.provider_job_id or "",
                    source="worker.poller._handle_completion",
                )
            else:
                record_unreserved_research_cost(
                    job_id=job.id,
                    provider=getattr(job, "provider", "") or "",
                    model=job.model,
                    actual_cost=float(cost or 0),
                    tokens=tokens,
                    request_id=job.provider_job_id or "",
                    source="worker.poller._handle_completion",
                )
        except Exception:
            logger.debug("cost_safety.record_cost failed for job %s", job.id, exc_info=True)
        return reservation

    async def _cleanup_completed_job(self, job: ResearchJob) -> None:
        """Remove provider uploads and clear their durable cleanup metadata."""
        from ..cli.commands.run_submission import cleanup_persisted_uploads

        if not await cleanup_persisted_uploads(self.provider, job):
            raise RuntimeError(f"Provider upload cleanup incomplete for completed job {job.id}")
        has_cleanup_metadata = bool(job.metadata.get("provider_file_ids") or job.metadata.get("vector_store_id"))
        if has_cleanup_metadata and not await self.queue.clear_cleanup_metadata(job.id):
            raise RuntimeError(f"Provider cleanup state missing for completed job {job.id}")

    async def _handle_completion(self, job: ResearchJob, response: ResearchResponse) -> None:
        """Handle job completion."""
        from ..queue.base import JobStatus

        try:
            logger.info(f"Job {job.id} completed, saving results")

            content = _response_content(response)

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
            cost = response.usage.cost if response.usage else None
            tokens = response.usage.total_tokens if response.usage else 0
            reservation = self._record_completion_cost(job, cost=cost, tokens=tokens)

            # Update queue with results
            results_updated = await self.queue.update_results(
                job_id=job.id, report_paths={"markdown": "report.md"}, cost=cost, tokens_used=tokens
            )
            if not results_updated:
                raise RuntimeError(f"Queue update_results failed for job {job.id}")
            if not reconcile_research_cost_from_ledger(reservation, job_id=job.id):
                raise RuntimeError(f"Canonical cost settlement missing for completed job {job.id}")

            await self._cleanup_completed_job(job)

            # Mark as completed
            status_updated = await self.queue.update_status(job.id, JobStatus.COMPLETED)
            if not status_updated:
                raise RuntimeError(f"Queue update_status(COMPLETED) failed for job {job.id}")
            # The job is no longer eligible for completion retries. Release the
            # in-process dedup key so a long-running poller does not retain one
            # string for every job it has ever completed.
            self._cost_controller_recorded_job_ids.discard(str(job.id))

            logger.info("Job %s completed successfully (cost: $%.4f)", job.id, cost or 0.0)

        except Exception:
            logger.exception("Error handling completion for job %s", job.id)
            # Provider completion is authoritative. Retain PROCESSING so the
            # next poll refetches durable cleanup evidence and retries local
            # finalization instead of rewriting completed provider work as failed.

    async def _handle_failure(
        self,
        job: ResearchJob,
        error: str,
        *,
        status: JobStatus = JobStatus.FAILED,
    ) -> None:
        """Close a terminal provider outcome and persist its local status."""
        try:
            logger.error("Job %s reached %s: %s", job.id, status.value, error)
            try:
                reservation = restore_research_cost_reservation(
                    job_id=job.id,
                    metadata=job.metadata,
                    provider=getattr(job, "provider", "") or "",
                    model=job.model,
                )
                if reservation is not None and job.provider_job_id:
                    settle_research_cost(
                        reservation,
                        actual_cost=None,
                        request_id=job.provider_job_id,
                        source="worker.poller._handle_failure",
                    )
                else:
                    refund_research_cost(reservation)
            except Exception:
                logger.exception("Failed to close provider cost for failed job %s", job.id)
                return

            from ..cli.commands.run_submission import cleanup_persisted_uploads

            if not await cleanup_persisted_uploads(self.provider, job):
                logger.error("Provider upload cleanup incomplete for failed job %s", job.id)
                return
            has_cleanup_metadata = bool(job.metadata.get("provider_file_ids") or job.metadata.get("vector_store_id"))
            if has_cleanup_metadata and not await self.queue.clear_cleanup_metadata(job.id):
                logger.error("Provider cleanup state missing for failed job %s", job.id)
                return

            status_updated = await self.queue.update_status(job_id=job.id, status=status, error=error)
            if not status_updated:
                logger.error("Failed to persist %s status for job %s", status.value.upper(), job.id)
                return
            self._cost_controller_recorded_job_ids.discard(str(job.id))

        except Exception:
            logger.exception("Error handling failure for job %s", job.id)


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
