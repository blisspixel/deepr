"""Simple API wrapper for submitting and managing research jobs."""

from datetime import datetime, timezone
from typing import Any, Optional

from deepr.config import AppConfig
from deepr.queue.base import JobStatus, ResearchJob
from deepr.queue.local_queue import SQLiteQueue


class ResearchAPI:
    """Simple API for submitting and managing research jobs."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.queue = SQLiteQueue()

    async def submit_research(
        self,
        prompt: str,
        mode: str = "focus",
        model: Optional[str] = None,
        provider: str = "openai",
        vector_store_id: Optional[str] = None,
        enable_web: bool = True,
        enable_code: bool = False,
        cost_limit: Optional[float] = None,
    ) -> str:
        """Submit a research job to the queue.

        Args:
            prompt: Research prompt
            mode: Research mode (focus, docs, project, team)
            model: Optional model override
            provider: AI provider
            vector_store_id: Optional vector store for context
            enable_web: Enable web search
            enable_code: Enable code interpreter
            cost_limit: Optional cost limit

        Returns:
            Job ID
        """
        # Determine model based on mode if not specified
        if not model:
            if mode == "team":
                model = "o3-deep-research"
            elif mode == "project":
                model = "o3-deep-research"
            elif mode == "docs":
                model = "o4-mini-deep-research"
            else:  # focus
                model = "o4-mini-deep-research"

        # Generate job ID
        import uuid

        job_id = f"research-{uuid.uuid4().hex[:6]}"

        # Create research job
        job = ResearchJob(
            id=job_id,
            prompt=prompt,
            model=model,
            provider=provider,
            status=JobStatus.QUEUED,
            submitted_at=datetime.now(timezone.utc),
            documents=[vector_store_id] if vector_store_id else [],
            enable_web_search=enable_web,
            enable_code_interpreter=enable_code,
            cost_limit=cost_limit,
        )

        # Submit to queue
        await self.queue.enqueue(job)

        return job.id

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
