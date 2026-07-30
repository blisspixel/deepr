"""Simple API wrapper for submitting and managing research jobs."""

from typing import Any

from deepr.config import AppConfig
from deepr.queue.base import JobStatus
from deepr.queue.local_queue import SQLiteQueue
from deepr.services.research_bounds import require_metered_interface_accounting


class ResearchAPI:
    """Simple API for submitting and managing research jobs."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.queue = SQLiteQueue()

    async def submit_research(
        self,
        prompt: str,
        mode: str = "focus",
        model: str | None = None,
        provider: str = "openai",
        vector_store_id: str | None = None,
        enable_web: bool = True,
        enable_code: bool = False,
        cost_limit: float | None = None,
    ) -> str:
        """Refuse the legacy queue path that cannot mint a durable reservation."""
        del prompt, mode, model, provider, vector_store_id, enable_web, enable_code, cost_limit
        require_metered_interface_accounting("services.research_api.submit_research")

    async def get_job_status(self, job_id: str) -> dict[str, Any]:
        """Get status of a research job.

        Args:
            job_id: Job ID

        Returns:
            Dictionary with status information
        """
        job = await self.queue.get_job(job_id)

        if not job:
            raise ValueError(f"Job not found: {job_id}")

        return {
            "id": job.id,
            "status": job.status.value,
            "prompt": job.prompt,
            "model": job.model,
            "provider": job.provider,
            "submitted_at": job.submitted_at.isoformat() if job.submitted_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "cost": job.cost,
            "error": job.last_error,
        }

    async def get_job_result(self, job_id: str) -> dict[str, Any]:
        """Get result of a completed research job.

        Args:
            job_id: Job ID

        Returns:
            Dictionary with result information
        """
        job = await self.queue.get_job(job_id)

        if not job:
            raise ValueError(f"Job not found: {job_id}")

        if job.status != JobStatus.COMPLETED:
            raise ValueError(f"Job not completed: {job.status.value}")

        return {
            "id": job.id,
            "status": job.status.value,
            "prompt": job.prompt,
            "report_paths": job.report_paths or {},
            "cost": job.cost,
            "tokens_used": job.tokens_used,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }

    async def cancel_job(self, job_id: str):
        """Cancel a research job.

        Args:
            job_id: Job ID
        """
        await self.queue.cancel(job_id)
