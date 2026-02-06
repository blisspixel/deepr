"""Azure Service Bus queue backend (planned for cloud deployment)."""

from typing import Any, Optional

from .base import JobStatus, QueueBackend, ResearchJob


class ServiceBusQueue(QueueBackend):
    """
    Azure Service Bus queue implementation (NOT IMPLEMENTED YET).

    This will be implemented for cloud deployment.
    For now, use SQLiteQueue for local development.
    """

    def __init__(self, connection_string: str, queue_name: str = "research-requests"):
        raise NotImplementedError("Azure Service Bus queue not implemented yet. Use SQLiteQueue for local development.")

    async def enqueue(self, job: ResearchJob) -> str:
        raise NotImplementedError()

    async def dequeue(self, worker_id: str) -> Optional[ResearchJob]:
        raise NotImplementedError()

    async def get_job(self, job_id: str) -> Optional[ResearchJob]:
        raise NotImplementedError()

    async def update_status(
        self,
        job_id: str,
        status: JobStatus,
        error: Optional[str] = None,
        provider_job_id: Optional[str] = None,
    ) -> bool:
        raise NotImplementedError()

    async def update_results(
        self,
        job_id: str,
        report_paths: dict[str, str],
        cost: Optional[float] = None,
        tokens_used: Optional[int] = None,
    ) -> bool:
        raise NotImplementedError()

    async def list_jobs(
        self,
        status: Optional[JobStatus] = None,
        tenant_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ResearchJob]:
        raise NotImplementedError()

    async def cancel_job(self, job_id: str) -> bool:
        raise NotImplementedError()

    async def get_queue_stats(self) -> dict[str, Any]:
        raise NotImplementedError()

    async def cleanup_old_jobs(self, days: int = 30) -> int:
        raise NotImplementedError()
